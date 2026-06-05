"""Public extraction API: orchestrate loaders -> resolver -> adapter -> classifier into a LineageResult.

Schema source is a pluggable mode (catalog / inferred / auto). A model's output columns come from the
RESOLVED schema (so it works identically whichever resolver produced it); a model with no resolved schema
is warned and skipped. Each model is processed under try/except (warn-and-continue) so one bad model
never aborts the run.
"""

from pathlib import Path

from dbt_column_lineage.artifacts import DbtArtifacts, load_artifacts
from dbt_column_lineage.changes import changed_from_explicit, changed_from_state
from dbt_column_lineage.classify import build_model_edges
from dbt_column_lineage.control import extract_controls, extract_operations
from dbt_column_lineage.hybrid import HybridSchemaResolver
from dbt_column_lineage.inference import InferredSchemaResolver
from dbt_column_lineage.ir import (
    ColumnDiff,
    ColumnRef,
    ControlEdge,
    LineageResult,
    ModelOperation,
    SelfReference,
)
from dbt_column_lineage.schema_resolver import CatalogSchemaResolver, SchemaMapping, SchemaResolver
from dbt_column_lineage.selection import select_nodes
from dbt_column_lineage.sql_adapter import build_sqlglot_schema, extract_column_lineage


def _catalog_source_seed(artifacts: DbtArtifacts) -> SchemaMapping:
    """Source schemas from the catalog, so inferred mode can still expand `SELECT *` from sources."""
    seed: SchemaMapping = {}
    for uid in artifacts.sources:
        entry = artifacts.catalog.get(uid)
        if entry is not None:
            seed[entry.relation.key()] = {c.name: c.type for c in entry.columns}
    return seed


def _resolve_changed(
    artifacts: DbtArtifacts, changed: list[str] | None, state_manifest: str | Path | None
) -> set[str]:
    if changed:
        return changed_from_explicit(artifacts, list(changed))
    if state_manifest:
        return changed_from_state(artifacts, state_manifest)
    return set()  # no change source -> hybrid degenerates to all-catalog


def _build_resolver(
    artifacts: DbtArtifacts,
    schema_mode: str,
    dialect: str,
    changed: list[str] | None,
    state_manifest: str | Path | None,
) -> SchemaResolver:
    has_catalog = bool(artifacts.catalog)
    mode = ("catalog" if has_catalog else "inferred") if schema_mode == "auto" else schema_mode
    if mode == "catalog":
        if not has_catalog:
            raise ValueError("schema-mode 'catalog' requires a catalog.json")
        return CatalogSchemaResolver(artifacts)
    if mode == "inferred":
        seed = _catalog_source_seed(artifacts) if has_catalog else {}
        return InferredSchemaResolver(artifacts, dialect, seed)
    if mode == "hybrid":
        if not has_catalog:
            raise ValueError("schema-mode 'hybrid' requires a catalog.json (for unchanged models)")
        return HybridSchemaResolver(
            artifacts, _resolve_changed(artifacts, changed, state_manifest), dialect
        )
    raise ValueError(
        f"unknown schema-mode: {schema_mode!r} (expected auto|catalog|inferred|hybrid)"
    )


def extract_lineage(
    manifest_path: str | Path,
    catalog_path: str | Path | None = None,
    *,
    schema_mode: str = "auto",
    select: str | None = None,
    dialect: str = "snowflake",
    changed: list[str] | None = None,
    state_manifest: str | Path | None = None,
) -> LineageResult:
    artifacts = load_artifacts(manifest_path, catalog_path)
    resolver = _build_resolver(artifacts, schema_mode, dialect, changed, state_manifest)
    schema_map = resolver.schema()
    sg_schema = build_sqlglot_schema(schema_map, dialect)  # build once, reuse for every model
    relation_to_uid = artifacts.relation_to_uid()

    edges = []
    warnings: list[str] = []
    processed: list[str] = []
    controls: list[ControlEdge] = []
    self_references: list[SelfReference] = []
    operations: list[ModelOperation] = []

    for uid in select_nodes(artifacts, select):
        node = artifacts.get_node(uid)
        if node is None or node.resource_type != "model" or not node.compiled_code:
            continue
        try:
            output_columns = [c.lower() for c in schema_map.get(node.relation.key(), {})]
            if not output_columns:
                warnings.append(f"no_schema:{uid}")
                continue
            raw = extract_column_lineage(node.compiled_code, output_columns, sg_schema, dialect)
            model_edges, model_warnings, model_self_refs = build_model_edges(
                node, raw, relation_to_uid, resolver, dialect
            )
            edges.extend(model_edges)
            warnings.extend(model_warnings)
            self_references.extend(model_self_refs)
            for control in extract_controls(node.compiled_code, sg_schema, dialect):
                up_uid = relation_to_uid.get(control.relation_key)
                if up_uid is not None and up_uid != uid:
                    controls.append(
                        ControlEdge(
                            uid, ColumnRef(up_uid, control.column.lower()), control.category
                        )
                    )
            ops = extract_operations(node.compiled_code, dialect)
            if ops is not None:
                operations.append(
                    ModelOperation(
                        asset=uid,
                        joins=ops.joins,
                        set_operation=ops.set_operation,
                        grouped=ops.grouped,
                        distinct=ops.distinct,
                        lateral_flatten=ops.lateral_flatten,
                        may_multiply_rows=ops.may_multiply_rows,
                        may_introduce_nulls=ops.may_introduce_nulls,
                    )
                )
            processed.append(uid)
        except Exception as exc:  # noqa: BLE001 - warn-and-continue: one model never aborts the run
            warnings.append(f"model_error:{uid}:{exc}")

    reconcile = getattr(resolver, "reconciliation", None)
    reconciliation: tuple[ColumnDiff, ...] = reconcile() if callable(reconcile) else ()

    return LineageResult(
        edges=tuple(edges),
        processed_assets=tuple(processed),
        warnings=tuple(dict.fromkeys(warnings)),
        reconciliation=reconciliation,
        controls=tuple(dict.fromkeys(controls)),
        self_references=tuple(dict.fromkeys(self_references)),
        operations=tuple(operations),
    )
