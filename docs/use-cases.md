# Use cases — dbt-column-lineage

Why a fact-only, column-level lineage IR is worth building, and what consumes it. This is a directional
map (kept current as priorities shift), not a commitment to build each as a feature here — the engine
stays general-purpose and lets each consumer add its own reasoning. The first-class consumer is the
separate [`dbt-test-lineage`](../../dbt-test-lineage) assurance tool; the rest validate that the IR
stays neutral and rich enough to serve more than one master.

Each use case lists the **engine facts it leans on** — a checklist that the IR must keep carrying.

## Primary

1. **Test / guarantee assurance** (→ `dbt-test-lineage`). Propagate `not_null`/`unique` (later
   `accepted_values`/`relationships`) through transforms to find redundant, missing, or contradicted
   tests. *Leans on:* transform chains (`CAST{safe}`, `CASE{else_null}`, `COALESCE` args,
   `JOIN{introduces_nulls}`), `operations` (grain, `may_multiply_rows`), `controls`.

2. **Impact analysis / blast radius.** "If I change, rename, or drop column X, which downstream columns
   and models break?" The transitive `downstream()` traversal over DIRECT edges answers this precisely
   at the column level — far tighter than model-level lineage. *Leans on:* DIRECT edge graph,
   `source_location`.

3. **Breaking-change detection in CI.** On a PR, diff the changed subgraph and surface columns whose
   type/derivation changed and the downstream columns affected. *Leans on:* hybrid mode +
   `reconciliation` (`ColumnDiff`), schema provenance.

## Secondary (the IR already supports; consumers add reasoning)

4. **PII / sensitive-data propagation.** Tag a source column as PII; follow value lineage to every
   downstream column that carries it (incl. through CTEs) → classification, masking, access policy.
   *Leans on:* DIRECT edges, `expression`. (Control/INDIRECT edges flag where a sensitive column merely
   filters vs. flows.)

5. **Root-cause / debugging.** "This output value looks wrong — where does it come from and what was
   done to it?" The transform chain gives the full step-by-step provenance. *Leans on:* `transforms`,
   `expression`, `source_location`.

6. **Refactor / migration safety.** Before rewriting a model, see exactly which downstream columns
   depend on each of its outputs and how. *Leans on:* edge graph, transform chains.

7. **Metadata / documentation propagation.** Push column descriptions, ownership, or classifications
   along lineage; auto-generate column-level lineage docs and graphs. *Leans on:* edges, Mermaid export.

8. **Performance / cost hints.** Surface fan-out joins, lateral flattens, and wide variant access that
   tend to blow up scan/compute. *Leans on:* `operations` (`may_multiply_rows`, `lateral_flatten`,
   joins), `STRUCT_ACCESS`/`UNNEST` steps.

## Design implication

The recurring theme: **consumers need facts, not the engine's opinions.** Every use case above is some
walk over the same neutral IR with consumer-specific reasoning on top. So the engine keeps recording
*what happened* (transforms, operations, controls, provenance, warnings) and resists baking in any one
consumer's verdicts — that is what keeps it serving all of these at once.
