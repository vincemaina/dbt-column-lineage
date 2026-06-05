# Architecture & Design

Status: **design phase, pre-code.** This document is the architectural source of truth and decision
log for the dbt column-lineage engine. It reflects decisions made jointly with the user and should be
updated as they evolve. For the ordered build plan see [`../ROADMAP.md`](../ROADMAP.md); for the first
milestone see [`phase-1-mvp.md`](./phase-1-mvp.md).

## 1. What this is

A general-purpose, open-source **column-lineage engine for dbt projects**. It consumes dbt artifacts +
compiled SQL and produces a neutral, richly-typed, machine-readable lineage graph, usable as a Python
library and a CLI. It is the **first of two projects**; a later test-lineage / assurance tool will
consume its output. No test-lineage-specific reasoning lives here. See the brief in
[`../notes/chatgpt/PROMPT.md`](../notes/chatgpt/PROMPT.md).

## 2. Locked decisions

These were settled in discussion and are load-bearing. Change them deliberately, in this doc.

1. **Build fresh on SQLGlot.** SQLGlot's `lineage()` is the underlying extractor (MIT, dependency-free,
   excellent Snowflake/CTE/union/window/lateral-flatten coverage, per-column DAG that carries the
   producing expression on each node). We do **not** fork Canva's `dbt-column-lineage-extractor` —
   we treat it as a reference implementation and may lift its dbt-selector parsing and Mermaid output.
2. **dbt compiles; we consume compiled SQL.** Model files are Jinja templates; faithfully expanding
   `ref()`/`source()`/macros is effectively reimplementing dbt. The engine **never parses raw Jinja**.
   It reads dbt's already-compiled SQL (`compiled_code` in `manifest.json`), Snowflake dialect.
3. **Decoupled artifact contract (for now).** The engine assumes `manifest.json` + `catalog.json`
   already exist (user runs `dbt compile` / `dbt docs generate`). A single wrapper command that runs
   dbt for the user is explicitly a **future** convenience.
4. **Schema is a pluggable provider with a provenance ladder.** Accuracy of column lineage depends on
   schema (without it, `SELECT *` → a `*` leaf and unqualified columns → `?`). Every resolved
   column/edge is tagged with where its schema came from:
   `catalog` (authoritative warehouse truth) → `inferred` (computed by parsing compiled SQL in DAG
   order) → `unknown` (degraded). **Declared YAML columns are never treated as schema authority.**
5. **Reconciliation = a feature, not just a fallback.** For a changed model we have both the *old
   authoritative* schema (catalog) and the *new inferred* schema (compiled SQL). Crossing them yields a
   column-level structural diff (added / removed / retyped columns) — the headline PR-review output.
6. **The IR is richer than column pairs.** Each edge carries the transformation expression and a
   transform category. We reserve a slot for control/INDIRECT lineage from day one (populated later),
   modelled on OpenLineage's DIRECT/INDIRECT taxonomy. OpenLineage is a (lossy) **export** adapter, not
   our internal model.

## 3. Pipeline stages

Modular boundaries so parsers / artifact versions / schema sources stay swappable:

```
dbt artifacts (manifest.json + catalog.json, compiled Snowflake SQL)
        │  [artifact loading]      → typed view of nodes, sources, parent/child maps, compiled_code
        ▼
   schema resolution               → SchemaResolver yields {relation: {column: type}} + provenance
        │  (catalog / inferred / hybrid)
        ▼
   per-model SQL analysis          → SQLGlot lineage() per output column, schema-fed
        │
        ▼
   IR construction                 → classify transform category, attach expression + provenance
        │
        ▼
   graph assembly + traversal      → direct edges; transitive upstream/downstream by graph walk
        │
        ▼
   serialization / export          → internal JSON · OpenLineage facet · Mermaid
        │
        ▼
   CLI presentation (Typer)        → extract · upstream · downstream · explain · graph
```

## 4. Intermediate representation (IR)

Conceptual shape (not final field names). The unit is a **column node**; edges point upstream
(downstream column ← its upstream contributors), mirroring SQLGlot.

```jsonc
// A column node identity
{ "asset": "model.my_project.orders", "column": "order_total" }

// A direct lineage edge
{
  "downstream": { "asset": "model.my_project.orders", "column": "order_total" },
  "upstream":   { "asset": "model.my_project.stg_orders", "column": "amount" },

  "lineage_type": "DIRECT",          // DIRECT (value) | INDIRECT (control) — INDIRECT reserved, not populated in MVP
  "transforms": [                    // ORDERED chain of EVERY operation, upstream -> downstream
    { "kind": "JOIN", "detail": { "join_type": "LEFT", "introduces_nulls": true } },
    { "kind": "CAST", "detail": { "to_type": "NUMBER(38, 2)" } }
  ],
  "expression": "CAST(amount AS NUMBER(38,2))",   // the full producing SQL, from SQLGlot Node.expression

  "schema_provenance": "catalog",    // catalog | inferred | unknown
  "confidence": "high",              // derived from provenance + resolution success
  "warnings": [],                    // e.g. "select_star_unresolved", "source_not_in_catalog"

  "dialect": "snowflake",
  "source_location": { "path": "models/marts/orders.sql", "node": "..." }  // when available
}
```

**Transform chain (`transforms`) — DIRECT / value lineage.** Each edge carries an **ordered list of
`TransformStep`s** capturing *every* operation the value passes through from upstream to downstream — not
a single category (which would be lossy: `c.first_name AS customer_first_name` under a LEFT JOIN is a
join + passthrough + rename, and a `not_null` guarantee's survival depends on knowing the join is
there). Each step has a `kind` and structured `detail` facts. Ordering follows the value's journey:
structural `JOIN` (row assembly) **before** value ops; `UNION` (branch combine) **after** a branch's ops.

- **kinds:** `IDENTITY`, `RENAME`, `CAST`, `COALESCE`, `CASE`, `AGGREGATION`, `WINDOW`, `EXPRESSION`,
  `UNION`, `JOIN` (structural), `UNKNOWN`.
- **detail facts** (examples): `JOIN → {join_type, introduces_nulls}`, `WINDOW → {func, role}`
  (role = `partition_by`/`order_by`/`value`), `AGGREGATION → {func}`, `CAST → {to_type}`,
  `COALESCE → {default}`, `RENAME → {from, to}`, `UNION → {branch}`.
- The engine records **facts only** — it does **not** judge whether a guarantee (e.g. not_null) survives
  the chain; that reasoning belongs to the consuming test-lineage tool. This keeps the engine
  general-purpose.
- **CTEs are collapsed, but the chain spans every hop.** A column flowing through multiple CTE/subquery
  layers (e.g. cast in CTE1 → rename in CTE2 → SUM in the final select) produces a single
  base-column→model-column edge whose `transforms` chain contains *all* hops in order. We walk SQLGlot's
  full lineage Node path (each hop's own projection) rather than only the final SELECT, threading the
  column name across renames. (Most tools — SQLLineage, DataHub, dbt, OpenLineage — collapse CTEs to
  endpoints and lose the per-hop chain; this is the gap OpenLineage issue #4090 is still trying to close.)

**Control categories (INDIRECT — reserved for a later phase):**
`JOIN`, `FILTER`, `GROUP_BY`, `SORT`, `WINDOW_PARTITION`, `CONDITIONAL`. Extracted by walking the
compiled SQL's WHERE / JOIN…ON / GROUP BY / QUALIFY / window clauses — which SQLGlot's `lineage()`
deliberately ignores.

**Direct vs transitive:** stored edges are direct (one hop). Transitive upstream/downstream is computed
on demand by a pure-Python graph walk with cycle guards (no extra storage).

**Model-level metadata (reserved):** some facts (joins performed, row multiplication, null
introduction) belong to the model/operation, not a single column edge. The IR reserves a place for
per-model operation metadata so we don't force everything onto edges. Populated in a later phase.

## 5. Schema resolution

A `SchemaResolver` interface returns a column→type map (and provenance) for any relation.

| Resolver | Source | Needs warehouse | Needs models built | Provenance | Phase |
|---|---|---|---|---|---|
| `CatalogSchemaResolver` | `catalog.json` | yes (already built) | yes | `catalog` | **MVP** |
| `InferredSchemaResolver` | parse compiled SQL in DAG order, seeded from catalog/sources | no | no | `inferred` | next |
| `HybridSchemaResolver` | catalog for unchanged models, inferred for changed; reconcile | partial | partial | mixed | later |

- **Inference** walks the (changed) subgraph in topological order: each model's output columns are
  computed by SQLGlot from its upstreams' schemas, becoming the input schema for models below it.
  Boundaries (unchanged upstreams, sources) are seeded from `catalog.json`.
- **Changed-set detection** (for hybrid mode) is itself pluggable: dbt `state:modified` (preferred —
  understands macro/ref ripple) or a git diff (simpler). A later concern.
- **`SELECT *`**: resolves correctly when the relation is in the active schema; otherwise degrades to a
  `*` leaf with a `select_star_unresolved` warning and `unknown` provenance — never silently guessed.

## 6. Outputs

- **Internal JSON** — the full IR; the stable machine-readable contract for downstream tools.
- **OpenLineage column-lineage facet** — lossy export adapter. Collapses our `transforms` chain onto the
  facet's DIRECT (IDENTITY/TRANSFORMATION/AGGREGATION) / INDIRECT (JOIN/GROUP_BY/FILTER/SORT/WINDOW)
  taxonomy. Note it has no field for confidence/ambiguity or the full chain — those stay in our model.
- **Mermaid** — graph visualization (reference: Canva's `flowchart TD` generation).

## 7. CLI surface (Typer)

Aligned with the brief; MVP implements the first three, later commands follow.

```
dbt-column-lineage extract   --manifest … --catalog … --select <dbt-selector> --output lineage.json
dbt-column-lineage upstream   model.column     # transitive ancestors
dbt-column-lineage downstream model.column     # transitive descendants
dbt-column-lineage explain    model.column     # show transform + expression per hop   (later)
dbt-column-lineage graph      model.column --format mermaid                              (later)
```

## 8. Explicit non-goals

- No Jinja/macro expansion (dbt's job).
- No test-lineage / assurance reasoning (the second project).
- No hosted service; runs locally / in CI.
- No silent guessing — prefer explicit `unknown` + warnings over a confident wrong edge.
- Python models and non-SQL assets are out of scope as lineage *sources* (they appear as endpoints).

## 9. Stack

Python 3.12 · `uv` (env/deps) · `pytest` · `Typer` (CLI) · `sqlglot[rs]` (pinned; the v30+ train moves
fast and does not promise semver). `src/` layout. Per-folder `CLAUDE.md` per the working conventions in
[`../claude-best-practices.md`](../claude-best-practices.md).

## 10. Key risks (carried from research)

- **SQLGlot API churn** — major v30, no semver guarantee; pin and isolate behind our own thin adapter.
- **Schema availability** — catalog requires a built warehouse; this is *the* constraint shaping the
  inferred/hybrid roadmap.
- **`SELECT *` / unqualified columns** — only as good as the schema we feed; must degrade honestly.
- **Snowflake specifics** — `LATERAL FLATTEN`, VARIANT/JSON paths, case-normalization; covered by
  SQLGlot but need fixture coverage.
- **Compiled-SQL dependency** — stale artifacts produce stale lineage; the tool should surface what it
  read and when, not pretend freshness.
