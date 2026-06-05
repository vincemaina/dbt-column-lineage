# dbt-column-lineage

**A local, static column-level lineage engine for dbt — that keeps the transformations, not just the connections.**

Most column-lineage tools answer *"column A feeds column B."* Useful, but they throw away the
interesting part: **what happened to the value in between.** When a column flows
`raw → cast in one CTE → coalesce in another → SUM in the final select → joined onto something`, almost
every tool collapses that to a single A→B edge.

This one doesn't. Every lineage edge carries the **ordered chain of every transformation** the value
passes through — across all CTE/subquery hops — and records *facts* (a `LEFT JOIN` can introduce nulls; an
aggregation changes cardinality) so a downstream data-quality / assurance tool can reason about whether a
guarantee like `not_null` or `unique` survives.

> ⚠️ **Status:** early-stage, Snowflake-first, built in the open. Core extraction + the schema-mode system
> are working and tested against a 729-model production Snowflake project; control-flow lineage and more
> dialects are on the roadmap.

---

## What an edge looks like

```jsonc
{
  "downstream": { "asset": "model.shop.order_enriched", "column": "customer_first_name" },
  "upstream":   { "asset": "model.shop.stg_customers",  "column": "first_name" },
  "lineage_type": "DIRECT",
  "transforms": [
    { "kind": "JOIN",   "detail": { "join_type": "LEFT", "introduces_nulls": true } },
    { "kind": "RENAME", "detail": { "from": "first_name", "to": "customer_first_name" } }
  ],
  "schema_provenance": "catalog",   // catalog | inferred | unknown — never a silent guess
  "confidence": "high"
}
```

The `transforms` chain spans every CTE hop (a column renamed in one CTE and aggregated in the next reads
as `[RENAME, AGGREGATION]`, not `UNKNOWN`), and carries structured facts: `CAST {to_type}`,
`WINDOW {func, role}`, `COALESCE {default}`, `AGGREGATION {func}`, etc.

## Quickstart

```bash
# 1. Produce dbt artifacts (the only step that touches your warehouse — metadata queries only)
dbt docs generate

# 2. Extract lineage (runs fully offline against the artifacts)
dbt-column-lineage extract --manifest target/manifest.json --catalog target/catalog.json --output lineage.json

# Trace a single column
dbt-column-lineage upstream   model.shop.orders.revenue --manifest target/manifest.json --catalog target/catalog.json
dbt-column-lineage downstream source.shop.raw.orders.amount --manifest target/manifest.json --catalog target/catalog.json

# Scope, or render a diagram
dbt-column-lineage extract --select +my_model --format mermaid --manifest ... --catalog ...
```

Install (from source, uses [`uv`](https://docs.astral.sh/uv/)):

```bash
git clone <repo> && cd dbt-column-lineage && uv sync
uv run dbt-column-lineage --help
```

## Schema modes — works with or without a built warehouse

The schema source is pluggable (`--schema-mode`):

| mode | needs | what it answers |
|---|---|---|
| `catalog` | manifest + catalog | authoritative lineage as **currently built** |
| `inferred` | manifest only | *"what would the lineage be from the code?"* — schemas computed from compiled SQL, **no warehouse** |
| `hybrid` | manifest + catalog + a change set | catalog for unchanged models, re-inferred for the changed subgraph |
| `auto` *(default)* | — | catalog if present, else inferred |

**Hybrid is the PR-review mode.** Point it at what you changed (`--changed my_model` or `--state prod_manifest.json`
for dbt `state:modified`) and it returns a column-level **reconciliation diff** — which columns your change
**adds, removes, or retypes** (types propagated from the upstream catalog types) — alongside the lineage.

## How it compares

| | Typical tools (SQLLineage, DataHub, dbt CLL, OpenLineage) | dbt-column-lineage |
|---|---|---|
| CTEs / subqueries | collapsed to endpoint A→B pairs | **ordered transform chain across every hop** |
| Transformations | flat / unordered tag at best | **sequenced** facts (cast → coalesce → join → agg …) |
| Schema source | usually require a built catalog | catalog **or** inferred-from-SQL **or** hybrid |
| PR workflow | — | **column-level reconciliation diff** |
| Footprint | often a hosted platform | **fully local & offline**, no service |
| Uncertainty | tends to guess | explicit provenance + confidence + warnings |

Notably, ordered per-hop transformation lineage is a gap the OpenLineage community has an
[open proposal](https://github.com/OpenLineage/OpenLineage/issues/4090) for — the standard can't represent
it yet. This engine treats that chain as the primary output.

## Design principles

- **Records facts, not verdicts** — captures *what happened* (joins, null introduction, aggregation,
  defaults) and stays general-purpose; leaves "does the guarantee hold?" to consumers.
- **Conservative** — degrades to explicit `unknown` + warnings rather than fabricating an edge.
- **Local & deterministic** — reads dbt artifacts, never connects to the warehouse; machine-readable
  JSON output (Mermaid for visuals).
- **Validated** — a hand-verified evaluation harness (edge precision/recall + transform-chain accuracy)
  plus real-repo invariant checks guard against regressions.

## Docs

- Architecture & decisions: [`docs/architecture.md`](docs/architecture.md)
- Roadmap: [`ROADMAP.md`](ROADMAP.md)
- Evaluation harness: [`tests/eval_harness.py`](tests/eval_harness.py)

## License

Open source — MIT.
