# Phase 1 Checklist

New here? Start at [`START_HERE.md`](./START_HERE.md).

Work top to bottom. Tick a box only when the task's *Definition of done* (see
[`README.md`](./README.md)) is fully satisfied. The **current task is the lowest unchecked box.**
**Review gate** tasks must be reviewed by Opus before the next task starts.

| # | Task | Review gate | Status |
|---|------|:-----------:|:------:|
| 01 | [Package scaffold & tooling](./task-01-scaffold.md) | no | ☑ |
| 02 | [Lineage IR data model](./task-02-ir.md) | **yes** | ☑ |
| 03 | [Synthetic test fixture + oracle](./task-03-fixture.md) | **yes** | ☑ |
| 04 | [Artifact loaders (manifest/catalog)](./task-04-loaders.md) | no | ☐ |
| 05 | [Catalog schema resolver](./task-05-catalog-resolver.md) | no | ☐ |
| 06 | [SQLGlot lineage adapter](./task-06-sqlglot-adapter.md) | **yes** | ☐ |
| 07 | [Transform classifier + edge builder](./task-07-transform-classifier.md) | **yes** | ☐ |
| 08 | [Lineage graph + transitive traversal](./task-08-graph.md) | no | ☐ |
| 09 | [Serializers (JSON + Mermaid)](./task-09-serializers.md) | no | ☐ |
| 10 | [dbt node selector](./task-10-selector.md) | no | ☐ |
| 11 | [CLI + end-to-end tests](./task-11-cli.md) | **yes** | ☐ |

## Execution model — who implements which task

Re-cut by difficulty (decided 2026-06-05). **When the lowest unchecked task is Opus-owned, Haiku must
stop and hand back** — do not implement it, even though the box is unchecked.

- **Opus implements:** 03 (fixture/oracle), 06 (sqlglot adapter), 07 (classifier). Co-reviews 11.
- **Haiku implements:** 04, 05, 08, 09, 10 — lighter review (tests+lint pass + spot-check; deep review
  reserved for the gate tasks).

So the Haiku run order is: **04 → 05 → [stop: Opus does 06, 07] → 08 → 09 → 10 → [11 together]**.

**Notes / handoffs** (Implementer fills in as tasks complete — e.g. resolved sqlglot version, deviations
approved by Opus, anything the next task should know):

- Task 01 complete: sqlglot version resolved to **30.9.0** (pinned via uv, in pyproject.toml)
- Opus review of task 01: approved. Capped `sqlglot[rs]` to `>=30.9.0,<31` (guard against the v31 major
  jump — architecture.md §10 risk #1). Task 06 targets the 30.x lineage API.
- **Dep change (Opus, task 03 prep):** `sqlglot[rs]` is **deprecated** in 30.9.0 ("no longer compatible
  with sqlglot"). Switched dependency to plain **`sqlglot>=30.9.0,<31`** (pure-Python; `sqlglot[c]` is a
  later perf option). Re-synced; lineage verified working.
- **Finding for task 06 (Opus, empirically verified vs sqlglot 30.9.0):** lineage leaf nodes report the
  table **alias** in `n.name` (e.g. `"O.ORDER_ID"`), NOT the relation. Read the real relation from
  `n.expression` (it's an `exp.Table`, use `exp.table_name(...)`, upper-cased); take the column from the
  last dotted segment of `n.name`. Confirmed: window cols surface both `partition by` + `order by`
  inputs; `select *` expands via schema; union fans out both branches.
- **IR change (Opus, after user feedback):** single `transform` category → ordered **`transforms`
  chain** of `TransformStep(kind, detail)` capturing EVERY operation (value ops + structural `JOIN` with
  `introduces_nulls`). `JOIN_DERIVED` removed. Engine records facts only (no guarantee-survival logic).
  Updated: `ir.py`, `test_ir.py`, `expected_lineage.json`, architecture §4, tasks 02/03/07. Task 04/05
  (loaders/resolver) are unaffected.
- **Task 03 complete (Opus):** `tests/fixtures/jaffle/` authored — 7 models, 2 sources, 26-edge oracle,
  all sqlglot-30.9.0-verified (source attributions match exactly; see `local/validate_fixture.py`).
  Handoffs for downstream tasks: (a) **output columns per model come from the catalog entry** (engine
  must enumerate from `catalog.json`, lower-cased); (b) **relation key = `DATABASE.SCHEMA.<alias|identifier>`,
  upper-cased** — this is what `relation_to_uid` and the sqlglot schema both key on; (c) sources use
  `identifier`, models use `alias`. Scratch validators live in gitignored `local/`.

---
_All 11 task files are written. Begin at [`START_HERE.md`](./START_HERE.md)._
