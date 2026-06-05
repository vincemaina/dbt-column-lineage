# Task 07 — Transform chain builder + edge builder

**Owner:** Opus · **Review gate:** YES · **Prerequisites:** tasks 01–06 · **Status:** see [CHECKLIST](./CHECKLIST.md)

> Updated for the **transform-chain IR** (an edge carries `transforms: tuple[TransformStep, ...]`, not a
> single category). See [`../architecture.md`](../architecture.md) §4, [`ir.py`](../../src/dbt_column_lineage/ir.py),
> and the oracle [`tests/fixtures/jaffle/expected_lineage.json`](../../tests/fixtures/jaffle/expected_lineage.json).

## Objective

Turn one model's raw SQLGlot lineage (task 06) into typed `LineageEdge`s, where each edge's `transforms`
is the **ordered chain of every operation** the value passes through (value ops + the structural JOIN),
and base-table relations are mapped back to dbt assets.

## Files to create

```
src/dbt_column_lineage/classify.py
tests/test_classify.py
```
(Add `classify.py` to `src/dbt_column_lineage/CLAUDE.md`.)

## Required interface

```python
@dataclass(frozen=True)
class JoinContext:
    anchor_relation: str | None                 # relation_key of the FROM anchor (no JOIN step)
    joined: dict[str, tuple[str, bool]]         # relation_key -> (join_type, introduces_nulls)

def extract_join_context(parsed: exp.Expression, dialect: str) -> JoinContext: ...

def build_transform_chain(
    select_expression: "exp.Expression",  # projection AST producing the output column
    output_column: str,
    upstream_column: str,                  # the specific upstream column this edge is for
    upstream_relation_key: str | None,
    join_context: JoinContext,
    is_set_operation: bool,
    branch_index: int | None,
) -> tuple[TransformStep, ...]: ...

def build_model_edges(
    node: ManifestNode,
    raw_lineage: list[RawColumnLineage],
    relation_to_uid: dict[str, str],
    resolver: SchemaResolver,
    dialect: str = "snowflake",
) -> tuple[list[LineageEdge], list[str]]:   # (edges, model-level warnings)
    ...
```

## Chain construction (the heart of this task)

Build the chain for **one (output_column, upstream_column) pair** as the value's journey, in order:

1. **Structural JOIN step (first, if applicable).** If `upstream_relation_key` is a *joined* relation
   (in `join_context.joined`, i.e. not the anchor), prepend
   `TransformStep(JOIN, {"join_type": <TYPE>, "introduces_nulls": <bool>})`.
   - `introduces_nulls`: `LEFT` → true for the right/joined side; `RIGHT` → true for the left side;
     `FULL` → true; `INNER`/`CROSS` → false. (In practice: a relation reached via `LEFT JOIN` is the
     nullable side, so true; the FROM anchor is never null-introduced.)
   - Columns from the FROM anchor get **no** JOIN step.

2. **Value operations (inner→outer over the projection AST).** Walk from the `upstream_column`'s
   `exp.Column` node outward to the projection root; emit one step per wrapping op:
   - `exp.Cast`/`exp.TryCast` → `CAST {"to_type": <rendered type>}`
   - `exp.Coalesce` (NVL/IFNULL normalize to this) → `COALESCE {"default": <non-column arg sql>}`
   - `exp.Case` → `CASE {}`
   - `exp.AggFunc` (Count/Sum/Avg/Min/Max/...) → `AGGREGATION {"func": <FUNC NAME>}`
   - `exp.Window` → `WINDOW {"func": <FUNC>, "role": <role>}` where role is `partition_by` /
     `order_by` / `value` depending on where `upstream_column` sits in the window (partition clause,
     order clause, or the windowed function's value args)
   - any other function/arithmetic wrapping a column → `EXPRESSION {}`

3. **Naming (last, for pure passthroughs only).** If **no** value op was emitted (the projection is a
   bare column passthrough):
   - `output_column == upstream_column` (case-insensitive) → append `IDENTITY {}`
   - else → append `RENAME {"from": upstream_column, "to": output_column}`
   When a value op *was* emitted, the alias is just the output name — do **not** add RENAME/IDENTITY.

4. **Set-operation step (very last).** If `is_set_operation`, append `UNION {"branch": branch_index}`.

A chain must always have ≥1 step; if nothing else applies, use `[TransformStep(UNKNOWN)]`.
All column-name comparisons are case-insensitive; emit column names lower-cased in `detail`.

## `build_model_edges` requirements

For each `RawColumnLineage` × each `RawSource`:
- **Map relation → asset:** `relation_to_uid[source.relation_key]`. If `relation_key` is None/unmapped →
  emit no edge; add model warning `"unmapped_relation:<key>"` (no silent guess).
- Build the chain via `build_transform_chain(...)`.
- Build the edge: `downstream=ColumnRef(node.unique_id, out.lower())`,
  `upstream=ColumnRef(up_uid, src.column.lower())`, `lineage_type=DIRECT`, `transforms=<chain>`,
  `expression=select_expression.sql(dialect=dialect)`,
  `schema_provenance=resolver.provenance(source.relation_key)`,
  `confidence=HIGH if provenance==CATALOG and not source.unresolved else LOW`,
  `warnings=<source warnings>`, `dialect=dialect`,
  `source_location=SourceLocation(node.original_file_path, node.unique_id)`.

## Verify

```bash
uv run pytest tests/test_classify.py
uv run ruff check . && uv run ruff format --check .
```

## Acceptance criteria

Running tasks 04→05→06→07 on the fixture, the edges for **each model** must match
`expected_lineage.json` exactly — compared on `(downstream, upstream, transforms)` where `transforms` is
compared as an ordered list of `(kind, detail)`. In particular:
- [ ] `stg_orders.order_id` → `[RENAME{from:id,to:order_id}]`; `amount` → `[CAST{to_type:NUMBER(38, 2)}]`.
- [ ] `stg_customers.first_name_clean` → `[COALESCE{default:'unknown'}]`.
- [ ] `customers.number_of_orders` → `[JOIN{LEFT,introduces_nulls:true}, AGGREGATION{func:COUNT}]`;
      `customers.customer_id` (FROM anchor) → `[IDENTITY]`.
- [ ] `order_enriched.customer_first_name` → `[JOIN{LEFT,introduces_nulls:true}, RENAME{first_name→customer_first_name}]`.
- [ ] `order_window.order_seq` → two edges: `[WINDOW{ROW_NUMBER,partition_by}]` (← customer_id) and
      `[WINDOW{ROW_NUMBER,order_by}]` (← ordered_at).
- [ ] `all_names.name` → `[RENAME{...→name}, UNION{branch:0}]` and `[RENAME, UNION{branch:1}]`.
- [ ] `star_passthrough.*` → `[IDENTITY]` per expanded column.
- [ ] Unmapped relation → `unmapped_relation:*` warning, no edge. Catalog-resolved edges are `HIGH`.
- [ ] `extract_join_context`, `build_transform_chain`, and detail facts have direct unit tests (not only
      via the fixture).

## Notes

Detail-key conventions are fixed in [`ir.py`](../../src/dbt_column_lineage/ir.py) `TransformStep`
docstring — match them exactly so the oracle comparison passes.
