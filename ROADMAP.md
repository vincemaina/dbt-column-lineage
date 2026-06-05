# Roadmap

High-level plan for the dbt column-lineage engine. Architecture and rationale:
[`docs/architecture.md`](./docs/architecture.md). Each phase links to a detailed plan as it is started.

The sequencing principle: get a **correct, authoritative** tool working first, then progressively relax
the warehouse dependency (inference), then add the diff-aware and control-lineage capabilities that make
it differentiated and ready to feed the future test-lineage tool.

## Phase 1 — Catalog-authoritative MVP  ✅ done

Whole-project lineage from `manifest.json` + `catalog.json` (authoritative Snowflake schema). Rich IR
(value lineage + **transform chains** + provenance), transitive traversal, JSON + Mermaid, CLI `extract` /
`upstream` / `downstream`. Detailed plan: [`docs/phase-1-mvp.md`](./docs/phase-1-mvp.md); task breakdown
in [`docs/tasks/`](./docs/tasks/). 85 tests, lint clean.

## Phase 2 — Schema inference (no warehouse)  ◑ in progress

**Done:** `InferredSchemaResolver` computes model schemas by qualifying compiled SQL in DAG order
(deriving source columns from usage first); pluggable **mode selector** (`auto`/`catalog`/`inferred`,
`catalog_path` optional, `--schema-mode` CLI). Engine takes output columns from the resolved schema.
Verified: inferred mode reproduces the fixture oracle and real-repo lineage (sem_granular 407=407 edges),
tagged `inferred` provenance. Plan: [`docs/phase-2-inference.md`](./docs/phase-2-inference.md).

## Phase 3 — Hybrid diff-aware mode + reconciliation  ✅ done

`HybridSchemaResolver`: catalog for unchanged models, inferred for the changed subgraph (changed models +
descendants). Per-changed-model **reconciliation** column-diff (`ColumnDiff`: added / removed / **retyped**
— types propagated from upstream catalog types via sqlglot `annotate_types`, with Snowflake type-name
normalization to suppress NUMBER↔DECIMAL / VARCHAR-length / TIMESTAMP_NTZ noise). Surfaced on
`LineageResult.reconciliation`. Pluggable change detection (`changes.py`): explicit names/uids + dbt
`state:modified` (compiled-SQL diff vs baseline). CLI: `--schema-mode hybrid --changed a,b` or
`--state baseline_manifest.json`. Verified on the real repo (provenance split + 100% of edges land on
declared dbt dependencies after filtering incremental `{{ this }}` self-edges). ← **Phases 2+3 complete.**
Next: Phase 4 (control/INDIRECT lineage).

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
