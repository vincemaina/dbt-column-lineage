"""Schema inference: compute each model's output column schema by qualifying its compiled SQL in DAG
(topological) order. Enables running without catalog.json — schemas come from the code. sqlglot-facing.

Two passes:
  1. derive each SOURCE relation's columns from how models reference it (sqlglot won't resolve a column
     to a source table unless that table is registered WITH its columns);
  2. infer each model's output columns in DAG order, seeding from sources + upstreams already computed.

Only column NAMES are inferred (sqlglot resolves lineage by name, not type); types are placeholders.
The module-level `infer_output_columns` / `topological_models` are shared with hybrid mode.
"""

from collections import defaultdict, deque

from sqlglot import exp, parse_one
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.annotate_types import annotate_types
from sqlglot.optimizer.qualify import qualify

from dbt_column_lineage.artifacts import DbtArtifacts
from dbt_column_lineage.ir import SchemaProvenance
from dbt_column_lineage.schema_resolver import SchemaMapping
from dbt_column_lineage.sql_adapter import build_sqlglot_schema

INFERRED_TYPE = "INFERRED"  # placeholder — lineage resolution needs column names, not types


def infer_output_columns(compiled_sql: str, schema, dialect: str = "snowflake") -> list[str]:
    """Output column names of a compiled query given its upstreams' schemas (expands SELECT *)."""
    try:
        qualified = qualify(
            parse_one(compiled_sql, dialect=dialect),
            schema=schema,
            dialect=dialect,
            validate_qualify_columns=False,
        )
    except SqlglotError:
        return []
    return [c for c in qualified.named_selects if c != "*"]


def infer_output_schema(compiled_sql: str, schema, dialect: str = "snowflake") -> dict[str, str]:
    """{OUTPUT_COL: type} via qualify + annotate_types — types propagate from the upstreams' (catalog)
    types. Type is 'UNKNOWN' where undeterminable (or for set-operation outputs)."""
    try:
        qualified = qualify(
            parse_one(compiled_sql, dialect=dialect),
            schema=schema,
            dialect=dialect,
            validate_qualify_columns=False,
        )
        annotated = annotate_types(qualified, schema=schema, dialect=dialect)
    except SqlglotError:
        return {}
    types: dict[str, str] = {}
    if isinstance(annotated, exp.Select):
        for sel in annotated.selects:
            name = sel.alias_or_name
            if name and name != "*":
                types[name.upper()] = sel.type.sql(dialect=dialect) if sel.type else "UNKNOWN"
    return {c.upper(): types.get(c.upper(), "UNKNOWN") for c in annotated.named_selects if c != "*"}


def topological_models(artifacts: DbtArtifacts) -> list[str]:
    """Model unique_ids, parents before children (Kahn's algorithm, deterministic; cycle-safe)."""
    models = {u for u, n in artifacts.nodes.items() if n.resource_type == "model"}
    parents = {u: {p for p in artifacts.parent_map.get(u, ()) if p in models} for u in models}
    children: dict[str, list[str]] = {u: [] for u in models}
    for u, deps in parents.items():
        for p in deps:
            children[p].append(u)
    indegree = {u: len(deps) for u, deps in parents.items()}
    queue = deque(sorted(u for u in models if indegree[u] == 0))
    order: list[str] = []
    while queue:
        u = queue.popleft()
        order.append(u)
        for c in sorted(children[u]):
            indegree[c] -= 1
            if indegree[c] == 0:
                queue.append(c)
    seen = set(order)
    order.extend(u for u in sorted(models) if u not in seen)  # cycle remnants, deterministically
    return order


def derive_source_columns(artifacts: DbtArtifacts, dialect: str = "snowflake") -> SchemaMapping:
    """Derive each non-model (source/seed) relation's columns from how models reference it."""
    source_relations = {n.relation.key() for n in artifacts.sources.values()}
    source_relations |= {
        n.relation.key() for n in artifacts.nodes.values() if n.resource_type != "model"
    }
    usage: dict[str, set[str]] = defaultdict(set)
    for node in artifacts.nodes.values():
        if node.resource_type != "model" or not node.compiled_code:
            continue
        try:
            parsed = parse_one(node.compiled_code, dialect=dialect)
        except SqlglotError:
            continue
        _collect_source_columns(parsed, source_relations, usage)
    return {rel: {c: INFERRED_TYPE for c in cols} for rel, cols in usage.items() if cols}


def _collect_source_columns(
    parsed: exp.Expression, source_relations: set[str], usage: dict[str, set[str]]
) -> None:
    source_aliases: dict[str, str] = {}
    all_aliases: set[str] = set()
    for table in parsed.find_all(exp.Table):
        alias = (table.alias_or_name or "").lower()
        all_aliases.add(alias)
        relation = exp.table_name(table).upper()
        if relation in source_relations:
            source_aliases[alias] = relation
    if not source_aliases:
        return
    # if the query reads exactly one table and it's a source, unqualified columns belong to it
    single_source = len(all_aliases) == 1 and len(source_aliases) == 1
    sole_relation = next(iter(source_aliases.values())) if single_source else None
    for column in parsed.find_all(exp.Column):
        if column.table:
            relation = source_aliases.get(column.table.lower())
            if relation:
                usage[relation].add(column.name.upper())
        elif sole_relation is not None:
            usage[sole_relation].add(column.name.upper())


class InferredSchemaResolver:
    """Computes model schemas from compiled SQL in DAG order. Implements the SchemaResolver protocol."""

    def __init__(
        self,
        artifacts: DbtArtifacts,
        dialect: str = "snowflake",
        seed: SchemaMapping | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._dialect = dialect
        self._seed = {k.upper(): dict(v) for k, v in (seed or {}).items()}
        self._schema: SchemaMapping | None = None
        self._provenance: dict[str, SchemaProvenance] = {}

    def schema(self) -> SchemaMapping:
        if self._schema is None:
            self._compute()
        assert self._schema is not None
        return self._schema

    def provenance(self, relation_key: str) -> SchemaProvenance:
        self.schema()
        return self._provenance.get(relation_key.upper(), SchemaProvenance.UNKNOWN)

    def _compute(self) -> None:
        derived = derive_source_columns(self._artifacts, self._dialect)
        base: SchemaMapping = {**derived, **self._seed}  # catalog seed wins over derived
        provenance: dict[str, SchemaProvenance] = {
            k: (SchemaProvenance.CATALOG if k in self._seed else SchemaProvenance.INFERRED)
            for k in base
        }
        accumulated = build_sqlglot_schema(base, self._dialect)
        result: SchemaMapping = dict(base)
        for uid in topological_models(self._artifacts):
            node = self._artifacts.nodes[uid]
            if node.resource_type != "model" or not node.compiled_code:
                continue
            relation = node.relation.key()
            columns = infer_output_columns(node.compiled_code, accumulated, self._dialect)
            if columns:
                column_map = {c.upper(): INFERRED_TYPE for c in columns}
                result[relation] = column_map
                provenance[relation] = SchemaProvenance.INFERRED
                accumulated.add_table(relation, column_map, dialect=self._dialect)
            else:
                provenance[relation] = SchemaProvenance.UNKNOWN
        self._schema = result
        self._provenance = provenance
