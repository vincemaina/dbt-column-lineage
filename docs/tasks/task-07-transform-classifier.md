# Task 07 — Transform classifier + edge builder

**Review gate:** YES · **Prerequisites:** tasks 01–06 · **Status:** see [CHECKLIST](./CHECKLIST.md)

## Objective

Turn one model's raw SQLGlot lineage (task 06) into typed `LineageEdge`s: classify each output column's
transform category and map base-table relations back to dbt assets. This produces the IR.

## Context

Read first: [`task-02-ir.md`](./task-02-ir.md) (`TransformCategory`, `LineageEdge`, `Confidence`,
`SchemaProvenance`) and [`../architecture.md`](../architecture.md) §4. May import `sqlglot` (to inspect
the `select_expression` AST) — the second and last module allowed to.

## Files to create

```
src/dbt_column_lineage/classify.py
tests/test_classify.py
```
(Add `classify.py` to `src/dbt_column_lineage/CLAUDE.md`.)

## Required interface (implement exactly)

```python
def classify_transform(
    select_expression: "exp.Expression",  # the projection AST for the output column
    output_column: str,
    upstream_column: str,
    is_set_operation: bool,
    upstream_is_join_anchor: bool,        # True if upstream relation is the FROM anchor; False if joined
) -> TransformCategory: ...

def build_model_edges(
    node: ManifestNode,
    raw_lineage: list[RawColumnLineage],
    relation_to_uid: dict[str, str],
    resolver: SchemaResolver,
    dialect: str = "snowflake",
) -> tuple[list[LineageEdge], list[str]]:   # (edges, model-level warnings)
    ...
```

## Classification rules (apply in this precedence order; first match wins)

1. `is_set_operation` is True → **UNION**.
2. AST contains an aggregate function (`exp.AggFunc`) → **AGGREGATION**.
3. AST contains a window (`exp.Window`) → **WINDOW**.
4. AST is/contains a `exp.Case` → **CASE**.
5. AST is/contains `exp.Coalesce` (or NVL/IFNULL normalized to it) → **COALESCE**.
6. AST is exactly a `exp.Cast`/`exp.TryCast` wrapping a single column → **CAST**.
7. AST is a bare `exp.Column` (passthrough):
   - `upstream_is_join_anchor` is False → **JOIN_DERIVED**.
   - else `output_column == upstream_column` (case-insensitive) → **IDENTITY**; otherwise → **RENAME**.
8. AST references ≥1 column via some other scalar expression → **EXPRESSION**.
9. Anything else → **UNKNOWN**.

(Names compared case-insensitively. If a rule is genuinely ambiguous for a fixture column, escalate
rather than guess — a wrong category fails the task-03 oracle.)

## `build_model_edges` requirements

For each `RawColumnLineage`, for each `RawSource`:

- **Map the relation:** `relation_to_uid[source.relation_key]` → upstream `unique_id`. If `relation_key`
  is None or unmapped → **do not emit an edge**; add a model warning `"unmapped_relation:<key>"` (no
  silent guess, no synthetic asset).
- **Determine join anchor:** the FROM-clause anchor relation of the model's query vs joined relations
  (inspect the parsed SQL once). Pass `upstream_is_join_anchor` accordingly.
- **Build the edge:** `downstream = ColumnRef(node.unique_id, output_column.lower())`,
  `upstream = ColumnRef(upstream_uid, source.column.lower())`, `lineage_type = DIRECT`,
  `transform = classify_transform(...)`, `expression = select_expression.sql(dialect=dialect)`,
  `schema_provenance = resolver.provenance(source.relation_key)`,
  `confidence = HIGH if provenance == CATALOG and not source.unresolved else LOW`,
  `warnings = source warnings`, `dialect = dialect`,
  `source_location = SourceLocation(node.original_file_path, node.unique_id)`.

Carry through any `RawColumnLineage.warnings` onto the edge or model warnings as appropriate.

## Verify

```bash
uv run pytest tests/test_classify.py
uv run ruff check . && uv run ruff format --check .
```

## Acceptance criteria

- [ ] Running tasks 04→05→06→07 on the fixture, the edges for **each model** match
      `expected_lineage.json` exactly (set comparison on `(downstream, upstream, transform)`):
      includes RENAME (`stg_orders.order_id`), CAST (`amount`), COALESCE (`first_name_clean`),
      AGGREGATION (`number_of_orders`), JOIN_DERIVED (`order_enriched.customer_first_name`),
      WINDOW (`order_window.order_seq`), UNION (`all_names.name`), IDENTITY passthroughs, and the
      `star_passthrough` IDENTITY edges.
- [ ] An unmapped relation produces a `unmapped_relation:*` warning and no edge.
- [ ] Edge `confidence` is HIGH for catalog-resolved fixture edges.
- [ ] `classify_transform` has direct unit tests per category (not only via the fixture).

## Open questions for Opus
_(Implementer: list any fixture column whose category you couldn't make match, with the AST you saw.)_
