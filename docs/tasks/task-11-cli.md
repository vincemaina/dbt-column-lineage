# Task 11 — Engine orchestration + CLI + end-to-end tests

**Review gate:** YES (final Phase 1 sign-off) · **Prerequisites:** tasks 01–10 · **Status:** see [CHECKLIST](./CHECKLIST.md)

## Objective

Wire all modules into the public extraction API and the Typer CLI (`extract`, `upstream`, `downstream`),
and prove the whole pipeline end-to-end against the fixture. This completes Phase 1.

## Context

Read first: [`../architecture.md`](../architecture.md) §3 (pipeline) and §7 (CLI), and every prior
task's interface. This task only *composes* existing modules — it should add little new logic beyond
orchestration and CLI plumbing.

## Files to create

```
src/dbt_column_lineage/engine.py     # public API: orchestration
src/dbt_column_lineage/cli.py         # extend the Typer app from task 01 with commands
tests/test_engine.py                  # end-to-end on the fixture
tests/test_cli.py                     # CLI via typer.testing.CliRunner
```
(Update `src/dbt_column_lineage/CLAUDE.md`.)

## Required interface (implement exactly)

```python
# engine.py
def extract_lineage(
    manifest_path: str | Path,
    catalog_path: str | Path,
    *,
    select: str | None = None,
    dialect: str = "snowflake",
) -> LineageResult: ...
```

### `extract_lineage` orchestration

1. `artifacts = load_artifacts(manifest_path, catalog_path)` (task 04).
2. `resolver = CatalogSchemaResolver(artifacts)`; `schema = resolver.schema()` (task 05).
3. `relation_to_uid = artifacts.relation_to_uid()`.
4. `selected = select_nodes(artifacts, select)` (task 10).
5. For each selected model with `compiled_code`:
   - Determine output columns from the model's catalog entry (lower-cased). If the model has **no
     catalog entry**, record a model warning `"no_catalog_entry:<uid>"` and skip (Phase 1 is
     catalog-authoritative).
   - `raw = extract_column_lineage(compiled_code, output_columns, schema, dialect)` (task 06).
   - `edges, warns = build_model_edges(node, raw, relation_to_uid, resolver, dialect)` (task 07).
   - Accumulate edges, warnings; append uid to `processed_assets`.
   - **Wrap each model in try/except** → on failure add `"model_error:<uid>:<msg>"` and continue
     (warn-and-continue; never abort the whole run for one model).
6. Return `LineageResult(edges=…, processed_assets=…, warnings=…)`.

### CLI (Typer)

```
dbt-column-lineage extract --manifest PATH --catalog PATH [--select SEL]
                           [--output PATH] [--format json|mermaid]
    # builds LineageResult, serializes (task 09); --output writes file, else prints to stdout; default format json

dbt-column-lineage upstream   COLUMN --manifest PATH --catalog PATH [--select SEL]
dbt-column-lineage downstream COLUMN --manifest PATH --catalog PATH [--select SEL]
    # COLUMN like 'model.jaffle.customers.lifetime_value'; build LineageResult -> LineageGraph (task 08)
    # -> print the transitive set, one 'asset.column' per line, deterministic order
```

- Print a concise warning summary to stderr (count + first few) when `result.warnings` is non-empty.
- Exit code 0 on success even with warnings; non-zero only on hard errors (bad path, unreadable JSON).

## Verify

```bash
uv run pytest                      # full suite incl. end-to-end
uv run ruff check . && uv run ruff format --check .
uv run dbt-column-lineage extract --manifest tests/fixtures/jaffle/manifest.json \
    --catalog tests/fixtures/jaffle/catalog.json --format json
uv run dbt-column-lineage upstream model.jaffle.customers.lifetime_value \
    --manifest tests/fixtures/jaffle/manifest.json --catalog tests/fixtures/jaffle/catalog.json
```

## Acceptance criteria

- [ ] `extract_lineage(fixture)` returns a `LineageResult` whose edge set equals
      `expected_lineage.json` (order-insensitive comparison on `(downstream, upstream, transform)`) — the
      definitive Phase 1 correctness check.
- [ ] `extract --format json` prints valid IR JSON; `--output` writes it; `--format mermaid` prints a
      `flowchart TD`.
- [ ] `upstream model.jaffle.customers.lifetime_value` includes `model.jaffle.stg_orders.amount` and the
      transitive source `source.jaffle.raw.raw_orders.amount`.
- [ ] `downstream source.jaffle.raw.raw_orders.amount` includes `stg_orders.amount` and
      `customers.lifetime_value`.
- [ ] A run with a model missing from the catalog warns and continues (no crash).
- [ ] Full suite green; ruff clean. Phase 1 done.

## Open questions for Opus
_(Implementer: surface any end-to-end mismatch vs the oracle here before final sign-off.)_
