# Task 06 — SQLGlot lineage adapter

**Review gate:** YES · **Prerequisites:** tasks 01–05 · **Status:** see [CHECKLIST](./CHECKLIST.md)

## Objective

Wrap SQLGlot's `lineage()` behind a thin, stable interface that, for one compiled model, returns each
output column's upstream **base-table** column contributions plus the producing expression. This is one
of only two modules allowed to import `sqlglot` (the other is task 07). Isolating it here contains
SQLGlot's API churn.

## Context

Read first: [`../architecture.md`](../architecture.md) §3–§4. Background on the SQLGlot API:
`sqlglot.lineage.lineage(column, sql, schema=..., dialect=...)` returns a `Node` whose `.downstream`
list are upstream nodes; leaf nodes whose `.expression` is a base table are the real sources; `.name`
is the qualified column. Without schema, `SELECT *` yields a `"*"` leaf and unresolved columns a `"?"`
placeholder — both must be reported as unresolved, never invented.
**If `vendor/` contains a clone of `canva-public/dbt-column-lineage-extractor`, read its
`extractor.py` for a working reference of walking the lineage tree** (reference only — do not copy its
limitations).

## Files to create

```
src/dbt_column_lineage/sql_adapter.py
tests/test_sql_adapter.py
```
(Add `sql_adapter.py` to `src/dbt_column_lineage/CLAUDE.md`.)

## Required interface (implement exactly)

```python
@dataclass(frozen=True)
class RawSource:
    relation_key: str | None   # base table as "DB.SCHEMA.TABLE" (UPPER) mapped from sqlglot, or None if unresolved
    column: str                # upstream column name as sqlglot reports it
    unresolved: bool           # True if this came from a "*" or "?" placeholder leaf

@dataclass(frozen=True)
class RawColumnLineage:
    output_column: str                 # the model output column (as sqlglot reports it)
    select_expression: "exp.Expression"# sqlglot AST of the producing projection (for task 07 to classify)
    is_set_operation: bool             # True if the model's top query is UNION/EXCEPT/INTERSECT
    sources: tuple[RawSource, ...]
    warnings: tuple[str, ...]          # e.g. "select_star_unresolved", "unresolved_column"

def extract_column_lineage(
    compiled_sql: str,
    output_columns: Iterable[str],
    schema: SchemaMapping,             # from task 05; flat relation_key -> {col: type}
    dialect: str = "snowflake",
) -> list[RawColumnLineage]:
    ...
```

## Requirements

1. Convert `SchemaMapping` to the structure SQLGlot expects. Build a `sqlglot.MappingSchema` (or nested
   `{db: {schema: {table: {col: type}}}}`) from each `relation_key` (`"DB.SCHEMA.TABLE"`), passing
   `dialect=dialect` so identifier normalization matches the SQL.
2. Parse `compiled_sql` once (`sqlglot.parse_one(sql, dialect=dialect)`); detect whether the top node is
   a set operation (`exp.Union`/`exp.Except`/`exp.Intersect`) → `is_set_operation`.
3. For each output column, call `lineage(column, parsed_or_sql, schema=…, dialect=…)`. Walk the returned
   `Node` tree (`.walk()` or recurse `.downstream`). For each **leaf** node:
   - base-table column → `RawSource(relation_key=<UPPER "db.schema.table">, column=<leaf col>, unresolved=False)`.
     Derive the qualified table from the leaf's table expression (e.g. `exp.table_name(...)`), upper-cased.
   - `"*"` leaf → one `RawSource(relation_key=None, column="*", unresolved=True)` + warning
     `"select_star_unresolved"`.
   - `"?"` / placeholder leaf → `RawSource(..., unresolved=True)` + warning `"unresolved_column"`.
4. Capture the top node's projection AST as `select_expression` (the `exp.Expression` that produces the
   output column — used by task 07 to classify the transform).
5. **Errors are contained:** a `SqlglotError`/`ParseError` for a column yields a `RawColumnLineage` with
   empty `sources` and a warning `"parse_error: <message>"`. Never raise out of `extract_column_lineage`.
6. Pin behaviour to the `sqlglot` version recorded in the CHECKLIST; do not rely on undocumented internals
   beyond what's needed.

## Verify

```bash
uv run pytest tests/test_sql_adapter.py
uv run ruff check . && uv run ruff format --check .
```

## Acceptance criteria

- [ ] For `stg_orders` SQL + fixture schema, `order_id` resolves to one source
      `("RAW.JAFFLE.RAW_ORDERS", "ID")`; `amount` to `("RAW.JAFFLE.RAW_ORDERS", "AMOUNT")`.
- [ ] `star_passthrough` (`select *`) with the fixture schema resolves to the four real
      `STG_CUSTOMERS` columns (no `"*"` leaf) — proving schema-fed star expansion works.
- [ ] With schema removed for a relation, the same `select *` degrades to one `unresolved=True` source
      with warning `"select_star_unresolved"` (a degrade test).
- [ ] `all_names` reports `is_set_operation == True` and `name`'s sources include both `FIRST_NAME` and
      `LAST_NAME` of `STG_CUSTOMERS`.
- [ ] A deliberately malformed SQL string yields a warned, empty-source result — no exception escapes.
- [ ] Only `sql_adapter.py` (and task 07) import `sqlglot`.

## Open questions for Opus
_(Implementer: if the leaf-node base-table detection is ambiguous against the installed sqlglot version,
stop and ask — include the sqlglot version and a minimal failing example.)_
