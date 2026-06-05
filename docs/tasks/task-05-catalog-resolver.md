# Task 05 — Catalog schema resolver

**Review gate:** no · **Prerequisites:** tasks 01–04 · **Status:** see [CHECKLIST](./CHECKLIST.md)

## Objective

Produce the schema map (relation → columns → type) the SQL adapter feeds to SQLGlot, sourced
authoritatively from `catalog.json`, plus per-relation provenance. This is the `CatalogSchemaResolver`
(the only resolver in Phase 1; inference/hybrid come in later phases).

## Context

Read first: [`../architecture.md`](../architecture.md) §5 (Schema resolution) and the `SchemaProvenance`
enum in [`task-02-ir.md`](./task-02-ir.md). Schema columns keep their catalog casing (UPPER for
Snowflake); the SQL adapter relies on SQLGlot's snowflake-dialect normalization to match SQL refs.

## Files to create

```
src/dbt_column_lineage/schema_resolver.py
tests/test_schema_resolver.py
```
(Add `schema_resolver.py` to `src/dbt_column_lineage/CLAUDE.md`.)

## Required interface (implement exactly)

```python
# A flat schema map: Relation.key() -> {column_name: sql_type}, both kept in catalog casing.
SchemaMapping = dict[str, dict[str, str]]

class SchemaResolver(Protocol):
    def schema(self) -> SchemaMapping: ...
    def provenance(self, relation_key: str) -> SchemaProvenance: ...

class CatalogSchemaResolver:
    def __init__(self, artifacts: DbtArtifacts) -> None: ...
    def schema(self) -> SchemaMapping: ...
    def provenance(self, relation_key: str) -> SchemaProvenance: ...
```

## Requirements

- `schema()` builds, for every catalog entry (models **and** sources), `Relation.key()` →
  `{CatalogColumn.name: CatalogColumn.type}`. Cache it (build once).
- `provenance(relation_key)` returns `SchemaProvenance.CATALOG` if that relation is in the catalog,
  else `SchemaProvenance.UNKNOWN`. (No `INFERRED` in Phase 1.)
- Pure: no SQLGlot import here. The adapter (task 06) converts `SchemaMapping` into SQLGlot's expected
  structure. Keep this module dependency-light.

## Verify

```bash
uv run pytest tests/test_schema_resolver.py
uv run ruff check . && uv run ruff format --check .
```

## Acceptance criteria

- [ ] `CatalogSchemaResolver(load_artifacts(fixture)).schema()` contains
      `"ANALYTICS.STAGING.STG_ORDERS"` → `{"ORDER_ID": "NUMBER", "CUSTOMER_ID": "NUMBER", ...}` with all
      five columns, and `"RAW.JAFFLE.RAW_ORDERS"` with its source columns.
- [ ] `provenance("ANALYTICS.STAGING.STG_ORDERS")` is `CATALOG`; `provenance("X.Y.Z")` (absent) is
      `UNKNOWN`.
- [ ] `STAR_PASSTHROUGH` resolves to the four `STG_CUSTOMERS` columns (from catalog).
- [ ] No `import sqlglot` in this module.
