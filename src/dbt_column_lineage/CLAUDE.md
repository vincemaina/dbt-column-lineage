# src/dbt_column_lineage/

Core engine modules for the dbt column-lineage tool. This package contains the lineage extraction
logic, artifact loading, schema resolution, and CLI interface.

## Modules

- `__init__.py` — package marker; exposes `__version__`.
- `ir.py` — immutable data model for column lineage (IR): enums, frozen dataclasses (incl. the
  `transforms` chain of `TransformStep`s), serializers.
- `artifacts.py` — load manifest.json + catalog.json into typed `DbtArtifacts` (relations, nodes,
  parent/child maps, catalog). The only module that knows the raw dbt JSON shape.
- `schema_resolver.py` — `CatalogSchemaResolver`: relation→{column: type} `SchemaMapping` + provenance.
- `sql_adapter.py` — thin SQLGlot wrapper: per output column, the upstream base-table sources +
  projection AST + join context + set-op branch index. (sqlglot-facing)
- `classify.py` — builds the `transforms` chain (value ops + structural JOIN) and `LineageEdge`s from
  the adapter's raw lineage; maps relations to dbt assets. (sqlglot-facing)
- `graph.py` — `LineageGraph` over edges: transitive `upstream`/`downstream`, cycle-safe; `parse_column_ref`.
- `serialize.py` — `to_json` / `write_json` / `to_mermaid` (deterministic output).
- `selection.py` — `select_nodes`: dbt selector subset (names, +ancestors/descendants+, path:, ∪/∩).
- `engine.py` — `extract_lineage(...)`: orchestrates loaders→resolver→adapter→classifier into a
  `LineageResult` (warn-and-continue per model). The public entrypoint other tools call.
- `cli.py` — Typer CLI: `extract` / `upstream` / `downstream`.
