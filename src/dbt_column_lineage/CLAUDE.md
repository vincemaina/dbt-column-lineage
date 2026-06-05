# src/dbt_column_lineage/

Core engine modules for the dbt column-lineage tool. This package contains the lineage extraction
logic, artifact loading, schema resolution, and CLI interface.

## Modules

- `__init__.py` — package marker; exposes `__version__`.
- `ir.py` — immutable data model for column lineage (IR): enums, frozen dataclasses, serializers.
- `cli.py` — Typer CLI application entrypoint.
