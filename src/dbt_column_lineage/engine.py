"""Public extraction API: orchestrate loaders -> resolver -> adapter -> classifier into a LineageResult.

Catalog-authoritative (Phase 1): output columns come from each model's catalog entry; a model with no
catalog entry is warned and skipped. Each model is processed under try/except (warn-and-continue) so one
bad model never aborts the whole run.
"""

from pathlib import Path

from dbt_column_lineage.artifacts import load_artifacts
from dbt_column_lineage.classify import build_model_edges
from dbt_column_lineage.ir import LineageResult
from dbt_column_lineage.schema_resolver import CatalogSchemaResolver
from dbt_column_lineage.selection import select_nodes
from dbt_column_lineage.sql_adapter import build_sqlglot_schema, extract_column_lineage


def extract_lineage(
    manifest_path: str | Path,
    catalog_path: str | Path,
    *,
    select: str | None = None,
    dialect: str = "snowflake",
) -> LineageResult:
    artifacts = load_artifacts(manifest_path, catalog_path)
    resolver = CatalogSchemaResolver(artifacts)
    sg_schema = build_sqlglot_schema(
        resolver.schema(), dialect
    )  # build once, reuse for every model
    relation_to_uid = artifacts.relation_to_uid()

    edges = []
    warnings: list[str] = []
    processed: list[str] = []

    for uid in select_nodes(artifacts, select):
        node = artifacts.get_node(uid)
        if node is None or node.resource_type != "model" or not node.compiled_code:
            continue
        try:
            entry = artifacts.catalog.get(uid)
            if entry is None:
                warnings.append(f"no_catalog_entry:{uid}")
                continue
            output_columns = [c.name.lower() for c in entry.columns]
            raw = extract_column_lineage(node.compiled_code, output_columns, sg_schema, dialect)
            model_edges, model_warnings = build_model_edges(
                node, raw, relation_to_uid, resolver, dialect
            )
            edges.extend(model_edges)
            warnings.extend(model_warnings)
            processed.append(uid)
        except Exception as exc:  # noqa: BLE001 - warn-and-continue: one model never aborts the run
            warnings.append(f"model_error:{uid}:{exc}")

    return LineageResult(
        edges=tuple(edges),
        processed_assets=tuple(processed),
        warnings=tuple(dict.fromkeys(warnings)),
    )
