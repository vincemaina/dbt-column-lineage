# Roadmap

High-level plan for the dbt column-lineage engine. Architecture and rationale:
[`docs/architecture.md`](./docs/architecture.md). Each phase links to a detailed plan as it is started.

The sequencing principle: get a **correct, authoritative** tool working first, then progressively relax
the warehouse dependency (inference), then add the diff-aware and control-lineage capabilities that make
it differentiated and ready to feed the future test-lineage tool.

## Phase 1 — Catalog-authoritative MVP  ← current

Whole-project lineage from `manifest.json` + `catalog.json` (authoritative Snowflake schema). Rich IR
(value lineage + transform category + provenance), transitive traversal, JSON + Mermaid, CLI `extract` /
`upstream` / `downstream`. Detailed plan: [`docs/phase-1-mvp.md`](./docs/phase-1-mvp.md).

## Phase 2 — Schema inference (no warehouse)

`InferredSchemaResolver`: compute model output schemas by parsing compiled SQL in DAG order, seeded from
catalog/sources. Enables a "local / code-state" mode that works without a freshly built catalog —
answers "what would the lineage be from the code as written?"

## Phase 3 — Hybrid diff-aware mode + reconciliation

`HybridSchemaResolver`: catalog for unchanged models, inferred for changed ones. Reconcile inferred vs
current catalog per changed model to produce a **column-level structural diff** (added / removed /
retyped) — the PR-review / impact-analysis headline. Pluggable changed-set detection (dbt
`state:modified` preferred, git diff fallback).

## Phase 4 — Control / INDIRECT lineage

Populate the reserved INDIRECT slot: columns used in joins, filters, group-by, sort, window
partitioning. Walk WHERE / JOIN…ON / GROUP BY / QUALIFY / window clauses (which SQLGlot's `lineage()`
ignores). Add reserved model-level operation metadata (joins, row multiplication, null introduction).
This is the capability the future test-lineage tool most depends on.

## Phase 5 — Interop, ergonomics, visualization

OpenLineage column-lineage facet export. `explain` / `graph --format mermaid` CLI commands. Optional
single wrapper command that runs `dbt compile` / `docs generate` for the user (closing the decoupled-
contract gap). Visualization polish.

## Deferred / out of scope

Test-lineage reasoning (the separate second project), Python models as lineage sources, non-Snowflake
dialects (config-pluggable but unprioritized), hosted service.
