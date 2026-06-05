# jaffle fixture

A tiny, fully-cataloged synthetic dbt project (artifacts only) used as the **correctness oracle** for
the lineage engine. Hand-authored; the expected lineage in `expected_lineage.json` was **verified
against sqlglot 30.9.0**, not just predicted. See [`../../../docs/tasks/task-03-fixture.md`](../../../docs/tasks/task-03-fixture.md).

## Files

- `manifest.json` / `catalog.json` — the only artifacts the engine reads (minimal consumed-field subset).
- `expected_lineage.json` — the oracle: every expected DIRECT (value) lineage edge.
- `models/*.sql` — the compiled SQL, one file per model, for human review. **Each file matches its
  `compiled_code` in `manifest.json` character-for-character** (no trailing newline).

## Relation map

Sources live in `RAW.JAFFLE`; models in `ANALYTICS.STAGING` (staging) and `ANALYTICS.MARTS` (marts).

| dbt unique_id | relation | columns out |
|---|---|---|
| `source.jaffle.raw.raw_orders` | `RAW.JAFFLE.RAW_ORDERS` | id, customer_id, amount, status, ordered_at |
| `source.jaffle.raw.raw_customers` | `RAW.JAFFLE.RAW_CUSTOMERS` | id, first_name, last_name |
| `model.jaffle.stg_orders` | `ANALYTICS.STAGING.STG_ORDERS` | order_id, customer_id, amount, status, ordered_at |
| `model.jaffle.stg_customers` | `ANALYTICS.STAGING.STG_CUSTOMERS` | customer_id, first_name, last_name, first_name_clean |
| `model.jaffle.customers` | `ANALYTICS.MARTS.CUSTOMERS` | customer_id, first_name, number_of_orders, lifetime_value |
| `model.jaffle.order_enriched` | `ANALYTICS.MARTS.ORDER_ENRICHED` | order_id, amount, customer_first_name |
| `model.jaffle.order_window` | `ANALYTICS.MARTS.ORDER_WINDOW` | order_id, customer_id, order_seq |
| `model.jaffle.all_names` | `ANALYTICS.MARTS.ALL_NAMES` | name |
| `model.jaffle.star_passthrough` | `ANALYTICS.MARTS.STAR_PASSTHROUGH` | (the 4 stg_customers columns) |

## What each model exercises

Each edge carries an ordered **transform chain** (`transforms`), not a single category — see
`expected_lineage.json`.

| model | transform chains under test |
|---|---|
| `stg_orders` | `[RENAME]` (`order_id`), `[CAST]` (`amount`), `[IDENTITY]` (others) |
| `stg_customers` | `[RENAME]` (`customer_id`), `[COALESCE]` (`first_name_clean`), `[IDENTITY]` |
| `customers` | `[JOIN, AGGREGATION]` (`number_of_orders`, `lifetime_value`), `[IDENTITY]` from FROM-anchor |
| `order_enriched` | `[JOIN, RENAME]` (`customer_first_name` — left-joined, null-introducing, then renamed) |
| `order_window` | `[WINDOW]` with `role` partition_by / order_by (`order_seq` ← two columns) |
| `all_names` | `[RENAME, UNION]` (`name` ← both set-operation branches) |
| `star_passthrough` | `SELECT *` schema-expansion → `[IDENTITY]` per expanded column |

## Notes on scope

- **Control lineage is out of Phase 1 scope.** The join keys, `group by`, and the window
  `partition by`/`order by` are *not* emitted as separate INDIRECT edges. The two `order_window.order_seq`
  WINDOW edges appear only because sqlglot surfaces projected-window inputs as value lineage.
- Sources and (future) seeds appear only as lineage **endpoints** — they have no `compiled_code`.
