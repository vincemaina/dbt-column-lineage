# Task 03 — Synthetic test fixture + lineage oracle

**Review gate:** YES (Opus must review before any code is built against it) · **Prerequisites:** task 02 · **Status:** see [CHECKLIST](./CHECKLIST.md)

## Objective

Hand-author a tiny, fully-cataloged dbt project's **artifacts** (`manifest.json` + `catalog.json`) plus
a **hand-verified expected-lineage oracle**. This is the correctness reference the whole engine is
tested against, so it must be exactly right — hence the Opus review gate.

## Why hand-authored (not generated)

Real artifacts come from `dbt compile` + `dbt docs generate` against Snowflake, which we can't run here.
So we author a **minimal** manifest/catalog containing *only the fields the engine consumes* (listed
below). Keep them minimal and readable.

## Files to create

```
tests/fixtures/jaffle/manifest.json
tests/fixtures/jaffle/catalog.json
tests/fixtures/jaffle/expected_lineage.json      # the oracle: expected DIRECT edges
tests/fixtures/jaffle/models/*.sql               # the compiled SQL, one file per model, for human review
tests/fixtures/jaffle/README.md                  # what each model exercises + the relation map
tests/fixtures/CLAUDE.md                          # folder index
```
The `models/*.sql` files are documentation/readability only; the engine reads `compiled_code` from
`manifest.json` (which must contain the identical SQL).

## Minimal consumed-artifact schema (authoritative for task 04 too)

**`manifest.json`** — only these fields are read:
```jsonc
{
  "nodes": {
    "<unique_id>": {
      "unique_id": "model.jaffle.stg_orders",
      "resource_type": "model",                 // "model" | "seed"
      "name": "stg_orders",
      "database": "ANALYTICS",
      "schema": "STAGING",
      "alias": "STG_ORDERS",                    // relation name; the engine uses alias (fallback: name)
      "compiled_code": "select ...",            // compiled Snowflake SQL (omit/empty for seeds & sources)
      "depends_on": { "nodes": ["model.jaffle.x", "source.jaffle.raw.raw_orders"] },
      "original_file_path": "models/staging/stg_orders.sql"
    }
  },
  "sources": {
    "source.jaffle.raw.raw_orders": {
      "unique_id": "source.jaffle.raw.raw_orders",
      "resource_type": "source",
      "name": "raw_orders",
      "database": "RAW", "schema": "JAFFLE", "identifier": "RAW_ORDERS"   // relation name = identifier
    }
  },
  "parent_map": { "<unique_id>": ["<parent unique_id>", ...] },
  "child_map":  { "<unique_id>": ["<child unique_id>", ...] }
}
```

**`catalog.json`** — only these fields are read:
```jsonc
{
  "nodes": {
    "model.jaffle.stg_orders": {
      "metadata": { "database": "ANALYTICS", "schema": "STAGING", "name": "STG_ORDERS" },
      "columns": {
        "ORDER_ID":    { "type": "NUMBER",       "name": "ORDER_ID",    "index": 1 },
        "CUSTOMER_ID": { "type": "NUMBER",       "name": "CUSTOMER_ID", "index": 2 }
      }
    }
  },
  "sources": { "source.jaffle.raw.raw_orders": { "metadata": {...}, "columns": {...} } }
}
```
Snowflake folds unquoted identifiers to UPPER CASE — store relation/column names **upper-case** in
`catalog.json`, exactly as Snowflake would. (The resolver normalizes case in task 05.)

## The project to encode

Two databases: sources in `RAW.JAFFLE`, models in `ANALYTICS.STAGING` / `ANALYTICS.MARTS`.

**Sources** (catalog only; no SQL): `RAW.JAFFLE.RAW_ORDERS(ID, CUSTOMER_ID, AMOUNT, STATUS, ORDERED_AT)`,
`RAW.JAFFLE.RAW_CUSTOMERS(ID, FIRST_NAME, LAST_NAME)`.

**Models** (`compiled_code`, exactly as written — each chosen to exercise one+ transform category):

`stg_orders` → `ANALYTICS.STAGING.STG_ORDERS`
```sql
select id as order_id, customer_id, cast(amount as number(38,2)) as amount, status, ordered_at
from RAW.JAFFLE.RAW_ORDERS
```
`stg_customers` → `ANALYTICS.STAGING.STG_CUSTOMERS`
```sql
select id as customer_id, first_name, last_name, coalesce(first_name, 'unknown') as first_name_clean
from RAW.JAFFLE.RAW_CUSTOMERS
```
`customers` → `ANALYTICS.MARTS.CUSTOMERS` (join + aggregation)
```sql
select c.customer_id, c.first_name,
       count(o.order_id) as number_of_orders, sum(o.amount) as lifetime_value
from ANALYTICS.STAGING.STG_CUSTOMERS c
left join ANALYTICS.STAGING.STG_ORDERS o on c.customer_id = o.customer_id
group by 1, 2
```
`order_enriched` → `ANALYTICS.MARTS.ORDER_ENRICHED` (passthrough from a joined, non-anchor table)
```sql
select o.order_id, o.amount, c.first_name as customer_first_name
from ANALYTICS.STAGING.STG_ORDERS o
left join ANALYTICS.STAGING.STG_CUSTOMERS c on o.customer_id = c.customer_id
```
`order_window` → `ANALYTICS.MARTS.ORDER_WINDOW` (window function)
```sql
select order_id, customer_id,
       row_number() over (partition by customer_id order by ordered_at) as order_seq
from ANALYTICS.STAGING.STG_ORDERS
```
`all_names` → `ANALYTICS.MARTS.ALL_NAMES` (union)
```sql
select first_name as name from ANALYTICS.STAGING.STG_CUSTOMERS
union all
select last_name as name from ANALYTICS.STAGING.STG_CUSTOMERS
```
`star_passthrough` → `ANALYTICS.MARTS.STAR_PASSTHROUGH` (`select *` expansion)
```sql
select * from ANALYTICS.STAGING.STG_CUSTOMERS
```

Catalog must list the real output columns of every model (e.g. `STG_ORDERS` →
`ORDER_ID, CUSTOMER_ID, AMOUNT, STATUS, ORDERED_AT`; `STAR_PASSTHROUGH` → the 4 columns of
`STG_CUSTOMERS`). `parent_map`/`child_map` must be consistent with the `from`/`join` relations.

## The oracle (`expected_lineage.json`)

> **REVISED (Opus):** edges now carry a `transforms` **chain** (ordered list of `{kind, detail}` steps),
> not a single `transform`. The authoritative oracle is the committed
> [`expected_lineage.json`](../../tests/fixtures/jaffle/expected_lineage.json) (already written &
> sqlglot-verified). The single-category examples below are superseded by the chain in that file; see
> [task 07](./task-07-transform-classifier.md) for the chain rules.

A list of expected **DIRECT** edges, each `{downstream:{asset,column}, upstream:{asset,column}, transform}`
using the `TransformCategory` values from [task 02](./task-02-ir.md). Column names lower-cased (engine
normalizes to lower). **Worked examples (these must appear):**

- `stg_orders.order_id` ← `source...raw_orders.id` — `RENAME`
- `stg_orders.amount` ← `raw_orders.amount` — `CAST`
- `stg_orders.customer_id` ← `raw_orders.customer_id` — `IDENTITY`
- `stg_customers.first_name_clean` ← `raw_customers.first_name` — `COALESCE`
- `customers.number_of_orders` ← `stg_orders.order_id` — `AGGREGATION`
- `customers.lifetime_value` ← `stg_orders.amount` — `AGGREGATION`
- `customers.customer_id` ← `stg_customers.customer_id` — `IDENTITY` (from the from-anchor)
- `order_enriched.customer_first_name` ← `stg_customers.first_name` — `JOIN_DERIVED` (joined, non-anchor)
- `order_window.order_seq` ← `stg_orders.customer_id` — `WINDOW`; and ← `stg_orders.ordered_at` — `WINDOW`
- `all_names.name` ← `stg_customers.first_name` — `UNION`; and ← `stg_customers.last_name` — `UNION`
- `star_passthrough.*` — one `IDENTITY` edge per expanded column of `stg_customers`

Author the **complete** edge set for all models (not only the examples). Control-lineage (the join key
`customer_id`, the `group by`, the window `partition by`/`order by` as *control* inputs) is **out of
scope** in Phase 1 — the window/order-by columns appear here only because SQLGlot surfaces projected
window inputs as value lineage; do not add separate INDIRECT edges.

## Verify

```bash
python -c "import json; json.load(open('tests/fixtures/jaffle/manifest.json')); json.load(open('tests/fixtures/jaffle/catalog.json')); json.load(open('tests/fixtures/jaffle/expected_lineage.json'))"
```
(All three parse as valid JSON. No engine code runs against them yet — that starts in task 04.)

## Acceptance criteria

- [ ] `manifest.json`, `catalog.json`, `expected_lineage.json` are valid JSON containing exactly the
      fields in the consumed-artifact schema above (plus the models/columns listed).
- [ ] Every model's `compiled_code` matches its `models/*.sql` file character-for-character.
- [ ] `catalog.json` lists correct output columns for every model and source (incl. `STAR_PASSTHROUGH`).
- [ ] `parent_map`/`child_map` are consistent with the SQL's relations.
- [ ] `expected_lineage.json` enumerates every DIRECT edge for every model, with the worked examples
      above present and correctly categorized.
- [ ] `README.md` maps each model → relation → which transform category it exercises.
- [ ] `tests/fixtures/CLAUDE.md` exists.

## Open questions for Opus
_(Implementer: add here and stop if anything is unclear — especially any edge whose transform category
you're unsure of. Better to ask than to encode a wrong oracle.)_
