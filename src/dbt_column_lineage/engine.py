"""Public extraction API: orchestrate loaders -> resolver -> adapter -> classifier into a LineageResult.

Schema source is a pluggable mode (catalog / inferred / auto). A model's output columns come from the
RESOLVED schema (so it works identically whichever resolver produced it); a model with no resolved schema
is warned and skipped. Each model is processed under try/except (warn-and-continue) so one bad model
never aborts the run.
"""

import multiprocessing as mp
from dataclasses import dataclass
from pathlib import Path

from dbt_column_lineage.artifacts import DbtArtifacts, load_artifacts
from dbt_column_lineage.changes import changed_from_explicit, changed_from_state
from dbt_column_lineage.classify import build_model_edges
from dbt_column_lineage.control import extract_controls, extract_operations, reads_from_stage
from dbt_column_lineage.ephemeral import (
    ephemeral_cte_map,
    ephemeral_schema,
    rewrite_ephemeral_ctes,
)
from dbt_column_lineage.hybrid import HybridSchemaResolver
from dbt_column_lineage.inference import InferredSchemaResolver
from dbt_column_lineage.ir import (
    ColumnDiff,
    ColumnRef,
    ControlEdge,
    LineageResult,
    ModelOperation,
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


@dataclass
class _Ctx:
    artifacts: DbtArtifacts
    schema_map: SchemaMapping
    sg_schema: object  # MappingSchema
    relation_to_uid: dict[str, str]
    resolver: SchemaResolver
    cte_map: dict[str, str]
    dialect: str


@dataclass
class _ModelOutput:
    uid: str
    edges: list
    warnings: list
    self_refs: list
    controls: list
    operation: ModelOperation | None
    processed: bool


def _process_uid(uid: str, ctx: _Ctx) -> _ModelOutput | None:
    """All per-model work for one model — pure given the prebuilt schema/ctx, so it runs identically in
    the sequential loop or a worker process. Returns None for non-model/empty nodes."""
    node = ctx.artifacts.get_node(uid)
    if node is None or node.resource_type != "model" or not node.compiled_code:
        return None
    try:
        output_columns = [c.lower() for c in ctx.schema_map.get(node.relation.key(), {})]
        if not output_columns:
            return _ModelOutput(uid, [], [f"no_schema:{uid}"], [], [], None, False)
        compiled = rewrite_ephemeral_ctes(node.compiled_code, ctx.cte_map, ctx.dialect)
        raw = extract_column_lineage(compiled, output_columns, ctx.sg_schema, ctx.dialect)
        model_edges, model_warnings, model_self_refs = build_model_edges(
            node, raw, ctx.relation_to_uid, ctx.resolver, ctx.dialect
        )
        warnings = list(model_warnings)
        if not model_edges and reads_from_stage(compiled, ctx.dialect):
            warnings.append(f"stage_source:{uid}")  # root ingestion model — no upstream is correct
        controls = []
        for control in extract_controls(compiled, ctx.sg_schema, ctx.dialect):
            up_uid = ctx.relation_to_uid.get(control.relation_key)
            if up_uid is not None and up_uid != uid:
                controls.append(
                    ControlEdge(uid, ColumnRef(up_uid, control.column.lower()), control.category)
                )
        ops = extract_operations(compiled, ctx.dialect)
        operation = (
            ModelOperation(
                asset=uid,
                joins=ops.joins,
                set_operation=ops.set_operation,
                grouped=ops.grouped,
                distinct=ops.distinct,
                lateral_flatten=ops.lateral_flatten,
                grain=ops.grain,
                may_multiply_rows=ops.may_multiply_rows,
                may_introduce_nulls=ops.may_introduce_nulls,
            )
            if ops is not None
            else None
        )
        return _ModelOutput(uid, model_edges, warnings, model_self_refs, controls, operation, True)
    except Exception as exc:  # noqa: BLE001 - warn-and-continue: one model never aborts the run
        return _ModelOutput(uid, [], [f"model_error:{uid}:{exc}"], [], [], None, False)


_PARALLEL_CTX: _Ctx | None = None  # set in the parent before forking workers; inherited via COW


def _process_uid_forked(uid: str) -> _ModelOutput | None:
    return _process_uid(uid, _PARALLEL_CTX)  # type: ignore[arg-type]


def extract_lineage(
    manifest_path: str | Path,
    catalog_path: str | Path | None = None,
    *,
    schema_mode: str = "auto",
    select: str | None = None,
    dialect: str = "snowflake",
    changed: list[str] | None = None,
    state_manifest: str | Path | None = None,
    workers: int = 1,
) -> LineageResult:
    artifacts = load_artifacts(manifest_path, catalog_path)
    resolver = _build_resolver(artifacts, schema_mode, dialect, changed, state_manifest)
    schema_map = dict(resolver.schema())
    sg_schema = build_sqlglot_schema(schema_map, dialect)  # build once, reuse for every model

    # Ephemeral re-attribution: register ephemeral relations (with inferred columns) and rewrite their
    # inlined CTEs so consumers' lineage stops at the ephemeral as a node (see ephemeral.py).
    cte_map = ephemeral_cte_map(artifacts)
    for relation, cols in ephemeral_schema(artifacts, sg_schema, dialect).items():
        schema_map.setdefault(relation, cols)  # keep catalog/inferred columns if already present
    if cte_map:
        sg_schema = build_sqlglot_schema(schema_map, dialect)  # rebuild with ephemeral relations
    relation_to_uid = artifacts.relation_to_uid()

    # Models are independent given the prebuilt schema, so processing is embarrassingly parallel.
    ctx = _Ctx(artifacts, schema_map, sg_schema, relation_to_uid, resolver, cte_map, dialect)
    uids = list(select_nodes(artifacts, select))
    if workers and workers > 1:
        global _PARALLEL_CTX
        _PARALLEL_CTX = ctx  # shared read-only via fork (COW) — only per-model results cross processes
        with mp.get_context("fork").Pool(workers) as pool:
            outputs = pool.map(_process_uid_forked, uids, chunksize=8)
    else:
        outputs = [_process_uid(uid, ctx) for uid in uids]

    edges = []
    warnings = []
    processed = []
    controls = []
    self_references = []
    operations = []
    for out in outputs:  # aggregate in selection order -> deterministic regardless of worker count
        if out is None:
            continue
        edges.extend(out.edges)
        warnings.extend(out.warnings)
        self_references.extend(out.self_refs)
        controls.extend(out.controls)
        if out.operation is not None:
            operations.append(out.operation)
        if out.processed:
            processed.append(out.uid)

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
