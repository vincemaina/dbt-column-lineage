# src/dbt_column_lineage/

Core engine modules for the dbt column-lineage tool. This package contains the lineage extraction
logic, artifact loading, schema resolution, and CLI interface.

## Modules

- `__init__.py` — package marker; exposes `__version__`.
- `ir.py` — immutable data model for column lineage (IR): enums, frozen dataclasses (incl. the
  `transforms` chain of `TransformStep`s), serializers.
- `artifacts.py` — load manifest.json + catalog.json into typed `DbtArtifacts` (relations, nodes,
  parent/child maps, catalog). The only module that knows the raw dbt JSON shape.
- `schema_resolver.py` — `SchemaResolver` protocol + `CatalogSchemaResolver`: relation→{column: type}
  `SchemaMapping` + provenance, from catalog.json. (no sqlglot)
- `inference.py` — `InferredSchemaResolver`: computes schemas from compiled SQL with no catalog —
  derives source columns from usage, then infers model schemas in DAG order. (sqlglot-facing)
- `sql_adapter.py` — thin SQLGlot wrapper: per output column, the upstream base-table sources +
  projection AST + join context + set-op branch index. (sqlglot-facing)
- `classify.py` — builds the `transforms` chain (value ops + structural JOIN) and `LineageEdge`s from
  the adapter's raw lineage; maps relations to dbt assets. (sqlglot-facing)
- `graph.py` — `LineageGraph` over edges: transitive `upstream`/`downstream`, cycle-safe; `parse_column_ref`.
- `serialize.py` — `to_json` / `write_json` / `to_mermaid` (deterministic output).
- `selection.py` — `select_nodes`: dbt selector subset (names, +ancestors/descendants+, path:, ∪/∩).
- `engine.py` — `extract_lineage(...)`: picks the schema resolver by mode (auto/catalog/inferred),
  orchestrates loaders→resolver→adapter→classifier into a `LineageResult` (warn-and-continue per model).
  Output columns come from the resolved schema (catalog or inferred). The public entrypoint.
- `cli.py` — Typer CLI: `extract` / `upstream` / `downstream` (`--catalog` optional, `--schema-mode`).
