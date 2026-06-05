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

## Phase 4 — Control / INDIRECT lineage  ◑ in progress

**4a done:** model-level **control inputs** — join keys, filter predicates (WHERE/HAVING/QUALIFY),
group-by (incl. positional `group by 1,2`), and sort columns — resolved to base sources through CTEs via
sqlglot's scope tree (`control.py`), on `LineageResult.controls`. Plus **self-reference capture**
(incremental `{{ this }}`) on `LineageResult.self_references`. Verified on the real repo
(all_sem_costs → 23 control edges: FILTER + GROUP_BY).
**4b done:** column-level INDIRECT edges — CASE-`WHEN`-condition columns and window `partition by`/
`order by` keys route to `lineage_type: INDIRECT` (`control: CONDITIONAL | WINDOW_PARTITION`) instead of
value edges (`classify._influence_category`); graph traversal is value-only (#7). Per-hop join detection
(#1) and multi-path capture (#3 — all distinct chains to a base column kept) also landed. **Remaining:**
reserved model-level operation metadata (row multiplication, null introduction). This is the capability
the test-lineage tool most needs.

## Phase 5 — Interop, ergonomics, visualization

OpenLineage column-lineage facet export. `explain` / `graph --format mermaid` CLI commands. Optional
single wrapper command that runs `dbt compile` / `docs generate` for the user (closing the decoupled-
contract gap). Visualization polish.

## Known limitations & accuracy gaps

Logged from an architecture review (2026-06-05). Severity = impact on lineage/test-lineage accuracy.

- **✅ #1 Join/null detection (was source-hop-only) — FIXED.** `RawSource.hops` now carries a per-hop
  join fact; `build_transform_chain` emits `JOIN` at the hop where it occurs, so joins *above* the source
  (e.g. a later-LEFT-joined CTE) are captured. Verified: `[IDENTITY, JOIN, RENAME]`; oracle preserved.
- **✅ #2 Value vs control conflation — FIXED.** Window `partition by`/`order by` keys and CASE
  `WHEN`-condition columns now route to **column-level INDIRECT edges** (`lineage_type: INDIRECT`,
  `control: WINDOW_PARTITION | CONDITIONAL`) instead of value edges; the windowed value / THEN value stay
  DIRECT. Verified on the real repo (375 DIRECT + 32 INDIRECT CONDITIONAL on sem_granular).
- **✅ #3 Multi-path to a base column — FIXED (capture all).** `extract_column_lineage`'s dedupe key now
  includes the full transform path (hop expressions + joins), so DISTINCT chains to the same base column
  are each emitted as their own edge (e.g. `coalesce(cte1.x, cte2.x)` resolving to one base via two
  routes), while genuinely identical paths still dedupe. Verified on the real repo (sem_granular: 8
  multi-chain pairs on `local_currency`, e.g. `[IDENTITY, JOIN, COALESCE]` vs `[IDENTITY, COALESCE]`).
  This also surfaces the sibling alternatives that #5 noted were implicit.
- **🟡 #4 `EXPRESSION` is a catch-all** (arithmetic / funcs / division collapse to one kind). Mitigated by
  the full `expression` SQL on every edge; could go granular (`FUNCTION{name}`/`ARITHMETIC{op}`) later.
- **🟡 #5 Sibling relationships implicit.** `coalesce(a,b)` emits two independent `COALESCE` edges; the
  "alternatives" relationship must be reconstructed by grouping on `(output, COALESCE)`.
- **🟠 #6 Ephemeral models** are inlined as CTEs by dbt — lineage likely traces *through* them to sources;
  the ephemeral may never appear as an intermediate asset. Needs verification on a repo with ephemerals.
- **✅ #7 Graph traversal lineage-type-aware — FIXED.** `LineageGraph` now indexes only DIRECT edges, so
  `upstream`/`downstream` follow value lineage and never traverse INDIRECT (control) edges.
- **🟢 #8 Cardinality / row-multiplication** (fan-out joins breaking uniqueness) not computed — inherently
  data-dependent; we expose join keys + group-by grain as facts for the consumer instead.
- **🟢 #9 Dialect hardcoded to Snowflake** in a few `.sql(dialect="snowflake")` / type calls; needs
  threading for multi-dialect.

## Deferred / out of scope

Test-lineage reasoning (the separate second project), Python models as lineage sources, non-Snowflake
dialects (config-pluggable but unprioritized), hosted service.
