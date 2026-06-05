# Phase 2 — Schema inference + pluggable schema modes

Status: **in progress.** This push delivers schema **inference** and a **mode selector** so the engine
can run from `catalog.json`, from `manifest.json` alone, or auto. Hybrid (catalog-for-unchanged /
inferred-for-changed + reconciliation) is the **next** push (decided: change-detection is pluggable —
explicit set + dbt `state:modified`).

## Why

Phase 1 is catalog-authoritative: it needs `dbt docs generate` (a built warehouse). Inference computes
each model's output columns from its **compiled SQL**, so lineage can run with only `manifest.json` —
no catalog, lighter warehouse footprint (only `dbt compile` needed).

## Modes (a pluggable `SchemaResolver` strategy)

| mode | resolver | needs | provenance |
|---|---|---|---|
| `catalog` | `CatalogSchemaResolver` (Phase 1) | manifest + catalog | `catalog` |
| `inferred` | `InferredSchemaResolver` (new) | manifest (catalog optional, seeds sources) | `inferred` (models), `catalog`/`unknown` (sources) |
| `auto` (default) | catalog if `catalog.json` present, else inferred | — | — |

`catalog_path` is now **optional**; `--schema-mode` selects the mode.

## How inference works

`InferredSchemaResolver` computes model schemas in **DAG (topological) order**: for each model, qualify
its compiled SQL against the schemas already known (sources seed + upstream models computed so far) and
read the output column **names** (`sqlglot` `qualify` → `named_selects`, which expands `SELECT *`). Add
that to the accumulating schema so downstream models resolve against it.

- Only **names** are inferred — `sqlglot` resolves lineage by name, not type; types are placeholders.
- **Seed**: source schemas come from `catalog.json` if present (so `SELECT * from a source` can expand).
  In pure `manifest`-only mode there is no source seed.
- **Honest limitation**: a source with no seed can't have `SELECT *` expanded → columns sourced that way
  degrade to `unknown`. **Model→model lineage with explicit columns still resolves fully** (verified:
  the jaffle fixture, which uses explicit columns, reproduces the full 26-edge oracle in `inferred` mode).

## Engine refactor

A model's **output column list** (which columns to trace) now comes from the **resolved schema**
uniformly (`schema_map[model.relation.key()]`), not the catalog — so it works identically for catalog or
inferred. Provenance (`catalog`/`inferred`/`unknown`) already flows onto every edge via the IR; inferred
edges carry `inferred` provenance (and `low` confidence — coarse, the provenance field is the precise
signal).

## Scope of this push

- `InferredSchemaResolver` (DAG-order inference) + tests.
- `load_artifacts(catalog optional)`, mode selector in `extract_lineage(schema_mode=…)`, `--schema-mode`
  CLI flag, output-columns-from-resolved-schema.
- Verify `inferred` mode reproduces the oracle edges on the fixture and runs on the real repo.

## Deferred to the next push (hybrid)

`HybridSchemaResolver` (catalog for unchanged models, inferred for changed), pluggable change detection
(explicit set + dbt `state:modified`), and the reconciliation column-diff (inferred-vs-catalog per
changed model = added/removed/retyped). Note: inference currently re-qualifies per model (once in the
resolver, once in extraction) — fine for the no-catalog convenience; optimize if it becomes hot.
