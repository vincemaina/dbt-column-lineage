"""Hybrid schema resolution: catalog (authoritative) for unchanged models, inferred (from current code)
for the changed subgraph; plus a reconciliation column-diff (inferred-vs-catalog) per directly-changed
model. The headline PR-review capability: "here's how your change alters the column lineage."

A model needs re-inference if it is directly changed OR descends from a changed model (its inputs
changed). Everything else keeps its authoritative catalog schema. sqlglot-facing via inference helpers.
"""

import re

from sqlglot import exp

from dbt_column_lineage.artifacts import DbtArtifacts
from dbt_column_lineage.inference import infer_output_schema, topological_models
from dbt_column_lineage.ir import ColumnDiff, SchemaProvenance
from dbt_column_lineage.schema_resolver import CatalogSchemaResolver, SchemaMapping
from dbt_column_lineage.sql_adapter import build_sqlglot_schema


def _canonical_type(type_str: str) -> str:
    """Normalize a type for comparison; suppress Snowflake noise (NUMBER↔DECIMAL, FLOAT↔DOUBLE,
    unbounded VARCHAR, TIMESTAMP_NTZ↔TIMESTAMP). 'UNKNOWN' means not comparable."""
    if not type_str or type_str.upper() == "UNKNOWN":
        return "UNKNOWN"
    try:
        canonical = (
            exp.DataType.build(type_str, dialect="snowflake").sql(dialect="snowflake").upper()
        )
    except Exception:  # noqa: BLE001 - unparseable type string: compare verbatim
        return type_str.upper()
    canonical = canonical.replace("VARCHAR(16777216)", "VARCHAR")
    return re.sub(r"TIMESTAMP_?NTZ", "TIMESTAMP", canonical)


def _types_differ(old: str, new: str) -> bool:
    a, b = _canonical_type(old), _canonical_type(new)
    return a != "UNKNOWN" and b != "UNKNOWN" and a != b


class HybridSchemaResolver:
    """Implements the SchemaResolver protocol; additionally exposes reconciliation() (column diffs)."""

    def __init__(
        self, artifacts: DbtArtifacts, changed_models: set[str], dialect: str = "snowflake"
    ) -> None:
        self._artifacts = artifacts
        self._dialect = dialect
        self._changed = {u for u in changed_models if u in artifacts.nodes}
        self._schema: SchemaMapping | None = None
        self._provenance: dict[str, SchemaProvenance] = {}
        self._reconciliation: tuple[ColumnDiff, ...] = ()

    def schema(self) -> SchemaMapping:
        if self._schema is None:
            self._compute()
        assert self._schema is not None
        return self._schema

    def provenance(self, relation_key: str) -> SchemaProvenance:
        self.schema()
        return self._provenance.get(relation_key.upper(), SchemaProvenance.UNKNOWN)

    def reconciliation(self) -> tuple[ColumnDiff, ...]:
        self.schema()
        return self._reconciliation

    def _inference_set(self) -> set[str]:
        """Changed models plus all their descendants (resolution depends on changed upstreams)."""
        models = {u for u, n in self._artifacts.nodes.items() if n.resource_type == "model"}
        out: set[str] = set()
        stack = list(self._changed)
        while stack:
            uid = stack.pop()
            if uid in out or uid not in models:
                continue
            out.add(uid)
            stack.extend(self._artifacts.child_map.get(uid, ()))
        return out

    def _compute(self) -> None:
        catalog_map = CatalogSchemaResolver(self._artifacts).schema()
        inference_set = self._inference_set()
        result: SchemaMapping = {}
        provenance: dict[str, SchemaProvenance] = {}
        accumulated = build_sqlglot_schema({}, self._dialect)

        # seed sources (non-model relations) from the catalog
        model_relations = {
            n.relation.key() for n in self._artifacts.nodes.values() if n.resource_type == "model"
        }
        for relation, cols in catalog_map.items():
            if relation not in model_relations and cols:
                result[relation] = cols
                provenance[relation] = SchemaProvenance.CATALOG
                accumulated.add_table(relation, cols, dialect=self._dialect)

        # models in DAG order: re-infer the changed subgraph, keep catalog for the rest
        for uid in topological_models(self._artifacts):
            node = self._artifacts.nodes[uid]
            if node.resource_type != "model" or not node.compiled_code:
                continue
            relation = node.relation.key()
            if uid in inference_set:
                cols = infer_output_schema(node.compiled_code, accumulated, self._dialect)
                prov = SchemaProvenance.INFERRED if cols else SchemaProvenance.UNKNOWN
            else:
                cols = catalog_map.get(relation, {})
                prov = SchemaProvenance.CATALOG if cols else SchemaProvenance.UNKNOWN
            provenance[relation] = prov
            if cols:
                result[relation] = cols
                accumulated.add_table(relation, cols, dialect=self._dialect)

        self._schema = result
        self._provenance = provenance
        self._reconciliation = self._reconcile(catalog_map, result)

    def _reconcile(
        self, catalog_map: SchemaMapping, result: SchemaMapping
    ) -> tuple[ColumnDiff, ...]:
        diffs: list[ColumnDiff] = []
        for uid in sorted(self._changed):
            node = self._artifacts.nodes.get(uid)
            if node is None or node.resource_type != "model":
                continue
            relation = node.relation.key()
            old = {
                c.lower(): t for c, t in catalog_map.get(relation, {}).items()
            }  # catalog (built)
            new = {c.lower(): t for c, t in result.get(relation, {}).items()}  # inferred (code)
            added = tuple(sorted(set(new) - set(old)))
            removed = tuple(sorted(set(old) - set(new)))
            retyped = tuple(
                (c, old[c], new[c])
                for c in sorted(set(old) & set(new))
                if _types_differ(old[c], new[c])
            )
            if added or removed or retyped:
                diffs.append(ColumnDiff(uid, added, removed, retyped))
        return tuple(diffs)
