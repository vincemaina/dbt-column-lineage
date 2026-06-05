# Phase 1 — Catalog-Authoritative MVP

Detailed plan for the first runnable version. Architecture context: [`architecture.md`](./architecture.md).
Roadmap position: [`../ROADMAP.md`](../ROADMAP.md).

## Goal

A correct, useful column-lineage tool that extracts lineage for a whole dbt project from
`manifest.json` + `catalog.json` (authoritative schema, Snowflake), produces the rich IR (value lineage
+ transform category + provenance), supports transitive traversal, and emits JSON + Mermaid. This proves
the plumbing and the IR before we take on schema *inference* (Phase 2).

## In scope

- Load `manifest.json` (nodes, sources, `parent_map`/`child_map`, `compiled_code`) and `catalog.json`
  (authoritative `{db.schema.table: {column: type}}`).
- `CatalogSchemaResolver` only.
- Per-output-column SQLGlot `lineage()` on compiled Snowflake SQL, schema-fed.
- Build the **direct-edge IR**: identity/asset, transform category, producing expression, schema
  provenance (`catalog` / `unknown`), warnings.
- Transform-category classification from `Node.expression`.
- Transitive `upstream` / `downstream` traversal (Python graph walk, cycle-safe).
- dbt node **selection syntax** subset (`+model`, `model+`, `+model+`, union/intersection, `tag:`,
  `path:`) — reference Canva's selector parser.
- Outputs: internal **JSON** + **Mermaid**.
- CLI (Typer): `extract`, `upstream`, `downstream`.
- Warn-and-continue error handling: per-column / per-model failures are caught, counted, surfaced — a
  failure degrades to an empty/`unknown` result that the caller can see, never a silent drop.

## Out of scope (later phases)

- Schema inference / `InferredSchemaResolver`, manifest/local mode (Phase 2).
- Hybrid diff-aware mode + reconciliation column-diff (Phase 3).
- Control / INDIRECT lineage (Phase 4) — but the IR **reserves the slot** now.
- OpenLineage export, `explain`/`graph` commands, single dbt-running wrapper command (Phase 5).
- Snapshots / Python models as lineage sources (appear as endpoints only).

## Test & evaluation strategy

- **Committed synthetic fixture** (`tests/fixtures/`): a small dbt project's *artifacts*
  (`manifest.json` + `catalog.json`, Snowflake-compiled) crafted to exercise rename, cast, expression,
  aggregation, window, CASE, COALESCE, CTE, join, union, `SELECT *`, plus a seed and a source. This
  backs the reproducible pytest suite and is the correctness oracle (hand-verified expected lineage).
- **Real-world validation** (manual, local only): the user's work dbt repo, cloned into the gitignored
  `local/` folder. Used to shake out real Snowflake patterns at scale. Its SQL is never committed or
  echoed into the repo.
- Unit tests per stage (loader, resolver, transform classifier, traversal) + end-to-end extract tests
  asserting expected edges on the fixture.

## Acceptance criteria

- `dbt-column-lineage extract --manifest … --catalog … --select <sel> --output lineage.json` produces
  IR JSON whose edges, transform categories, and provenance match the hand-verified fixture.
- `upstream` / `downstream model.column` return correct transitive sets on the fixture.
- `SELECT *` against a cataloged relation resolves to real columns; against an uncataloged one degrades
  to a warned `unknown` (never a wrong guess).
- Runs clean on the user's real repo with a warning summary (no crashes), pending manual spot-checks.

## Rough build order

1. Package scaffold (`src/` layout, `pyproject.toml` deps, `uv`, pytest, Typer entrypoint, CI).
2. Synthetic fixture artifacts + expected-lineage oracle.
3. Artifact loaders (typed manifest/catalog views).
4. `CatalogSchemaResolver`.
5. SQLGlot adapter (thin, isolates version churn) + per-column lineage.
6. Transform-category classifier + IR construction.
7. Graph assembly + transitive traversal.
8. JSON + Mermaid serializers.
9. dbt selector parser.
10. CLI wiring + end-to-end tests.
