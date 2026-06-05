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

## Phase 2 — Schema inference (no warehouse)  ✅ done

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

## Phase 4 — Control / INDIRECT lineage  ✅ done

**4a done:** model-level **control inputs** — join keys, filter predicates (WHERE/HAVING/QUALIFY),
group-by (incl. positional `group by 1,2`), and sort columns — resolved to base sources through CTEs via
sqlglot's scope tree (`control.py`), on `LineageResult.controls`. Plus **self-reference capture**
(incremental `{{ this }}`) on `LineageResult.self_references`. Verified on the real repo
(all_sem_costs → 23 control edges: FILTER + GROUP_BY).
**4b done:** column-level INDIRECT edges — CASE-`WHEN`-condition columns and window `partition by`/
`order by` keys route to `lineage_type: INDIRECT` (`control: CONDITIONAL | WINDOW_PARTITION`) instead of
value edges (`classify._influence_category`); graph traversal is value-only (#7). Per-hop join detection
(#1) and multi-path capture (#3 — all distinct chains to a base column kept) also landed.
**Model-level operation metadata DONE:** `control.extract_operations` →
`LineageResult.operations` (`ModelOperation` per model) records the constructs bearing on cardinality /
nullability — joins (+types), top-level set operation, GROUP BY, DISTINCT, lateral-flatten — plus
`may_multiply_rows` / `may_introduce_nulls` possibility flags (facts, not verdicts; join keys + group-by
grain themselves stay in `controls`). **Phase 4 complete.** This is the capability the test-lineage tool
most needs.

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
- **✅ #4 `EXPRESSION` granularity — FIXED.** EXPRESSION steps now carry `detail`: `{"func": <name>}` for
  named scalar functions, `{"op": <add|sub|mul|div|...>}` for arithmetic. Two new kinds also added:
  `STRUCT_ACCESS` (variant/json field extraction, with the key `path`) and `UNNEST` (lateral flatten /
  explode). Verified on the real repo: a flatten model's chains went `[UNKNOWN,…]` →
  `[UNNEST, JOIN, STRUCT_ACCESS, CAST]` (32 UNKNOWN chains → 0).
- **✅ #5 Coalesce siblings — FIXED.** COALESCE steps carry `{"arg_index", "arg_count"}`, so the ordered
  "alternatives" relationship is explicit (group on `(output, COALESCE)` and read `arg_index`).
- **✅ #6 Ephemeral models — FIXED (re-attributed as nodes).** `ephemeral.py` registers each ephemeral's
  relation (inferred columns) and stubs the inlined `__dbt__cte__<name>` CTE body to `SELECT * FROM
  <relation>`, so consumer lineage stops at the ephemeral as a real intermediate node and the ephemeral
  is still analyzed as its own model. Verified on the real repo (content_items_agg_discovery: 17 edges
  in, 17 out, graph traverses through it).
- **✅ #7 Graph traversal lineage-type-aware — FIXED.** `LineageGraph` now indexes only DIRECT edges, so
  `upstream`/`downstream` follow value lineage and never traverse INDIRECT (control) edges.
- **✅ #8 Cardinality / row-multiplication — ADDRESSED (facts, not verdicts).** Won't compute true
  cardinality (data-dependent); the model-level operation metadata (`LineageResult.operations`) exposes
  joins, set ops, grouping, distinct, lateral-flatten + `may_multiply_rows` / `may_introduce_nulls`
  possibility flags, and join keys + group-by grain live in `controls`.
- **✅ #9 Dialect hardcoded — FIXED.** `dialect` is threaded through `build_transform_chain` → value
  steps (CAST type, coalesce default render) and `hybrid._canonical_type`. No `"snowflake"` literals
  remain on the extraction path except the default argument values.

### New gaps found in the 2026-06-05 deep audit (real 729-model repo)

- **✅ #10 Semi-structured / VARIANT access — FIXED.** 236 models use `col:field::type`; now classified
  as `STRUCT_ACCESS` with the key path (see #4).
- **✅ #11 `LATERAL FLATTEN` / UNNEST hop was `UNKNOWN` — FIXED.** 56 models; the row-exploding hop is now
  the `UNNEST` kind (see #4).
- **✅ #12 Stage / external sources — FIXED (clear signal).** `FROM @stage` root ingestion models
  correctly produce 0 edges; the engine now emits an informative `stage_source:<uid>` warning instead of
  a misleading `unresolved_column`. (`control.reads_from_stage`.)
- **✅ #13 `GROUP BY ALL` — FIXED.** 8 models; `_group_columns` now expands `GROUP BY ALL` to every
  non-aggregate select expression, so those group keys appear in `controls` (GROUP_BY).
- **🟢 #14 PIVOT / UNPIVOT** (13 models) — pivot output columns are data-dependent (pivot values become
  column names). Extraction does not crash and produces value edges for the static parts; sub-column
  lineage through the pivot is not modelled. Documented limitation; revisit if a consumer needs it.
- **🟢 #15 Quoting / case-sensitivity.** Column names are normalized to lower-case (Snowflake folds
  unquoted identifiers to upper). A *quoted* mixed-case identifier (`"MixedCase"`) that must preserve
  case could in principle mismatch; not observed in the real repo. Documented; revisit if it surfaces.
- **🟢 #16 Recursive CTEs** (1 model) — handled safely (cycle/depth guards in the path walker); verified
  no crash/hang (52 edges, 0.3s). Lineage through the recursive term is best-effort.

### Null/cardinality semantic facts added in the independent adversarial audit (2026-06-05)

These were surfaced by a second-pass review focused on what the test-lineage tool needs for
`not_null`/`unique` reasoning. All are `detail` enrichments (no new kinds) and are tested in
`tests/test_classify.py`.

- **✅ #17 `TRY_CAST` vs `CAST`.** Both are `exp.Cast`; `TRY_CAST` now carries `{"safe": true}` — it
  yields NULL on conversion failure (a null-introduction), whereas `CAST` errors. Critical for not_null.
- **✅ #18 `CASE` else-NULL.** CASE steps carry `{"else_null": bool}` — true when unmatched rows yield
  NULL (no `ELSE`, or `ELSE NULL`), the silent null-introduction the audit flagged as HIGH.
- **✅ #19 `COUNT(DISTINCT x)`.** AGGREGATION steps carry `{"distinct": true}` when the aggregate
  dedups — relevant to `unique` reasoning; previously indistinguishable from `COUNT(x)`.
- **✅ #20 `NULLIF`.** Recorded as `EXPRESSION {"func": "NULLIF", "introduces_nulls": true}` (returns
  NULL when its two args are equal).
- **✅ #21 Window frame.** WINDOW steps carry `{"frame": "ROWS BETWEEN ..."}` when a ROWS/RANGE frame is
  present — affects which rows feed the value.
- **🟢 #22 Correlated-subquery predicate columns.** A correlation column in a scalar/EXISTS subquery's
  WHERE (`... where b.aid = a.id`) is not surfaced as a source — sqlglot's `lineage()` treats subqueries
  as opaque. The full `expression` SQL on the edge preserves it as an escape hatch. Documented; would
  need bespoke subquery traversal to lift into structured facts.

## Deferred / out of scope

Test-lineage reasoning (the separate second project), Python models as lineage sources, non-Snowflake
dialects (config-pluggable but unprioritized), hosted service.
