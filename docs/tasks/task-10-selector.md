# Task 10 — dbt node selector

**Review gate:** no · **Prerequisites:** tasks 01, 04 · **Status:** see [CHECKLIST](./CHECKLIST.md)

## Objective

Resolve a dbt-style selection string to a set of model `unique_id`s, so `extract` can scope to part of a
project. A pragmatic subset of dbt's selector syntax — enough for Phase 1.

## Context

Read first: [`task-04-loaders.md`](./task-04-loaders.md) (`DbtArtifacts`, `parent_map`/`child_map`).
If `vendor/` has the Canva extractor, `_parse_selectors` in its `extractor.py` is a reference.

## Files to create

```
src/dbt_column_lineage/selection.py
tests/test_selection.py
```
(Add `selection.py` to `src/dbt_column_lineage/CLAUDE.md`.)

## Required interface (implement exactly)

```python
def select_nodes(artifacts: DbtArtifacts, selector: str | None) -> list[str]:
    """ Return matching model unique_ids (deterministic, sorted). selector=None or "" -> all models. """
```

## Supported syntax (Phase 1 subset)

- `None` / empty → all models (`resource_type == "model"`).
- Bare name: `stg_orders` → the model whose `name` matches (resolve name → unique_id).
- Graph operators (ancestors/descendants via `parent_map`/`child_map`, transitive, full depth):
  - `+stg_orders` → `stg_orders` + all ancestors.
  - `stg_orders+` → `stg_orders` + all descendants.
  - `+stg_orders+` → both.
- `path:models/staging` → models whose `original_file_path` starts with that path.
- **Union** = space-separated: `a b` → matches of `a` ∪ matches of `b`.
- **Intersection** = comma-separated: `a,b` → matches of `a` ∩ matches of `b`.

Out of scope for Phase 1 (do **not** implement; if requested, ignore with a note): `tag:`, `package:`,
numeric depth (`2+model`), `source:`, `@`, result/state selectors. Only **models** are returned (seeds
and sources are never selection targets, though they appear as ancestors in lineage).

## Requirements

- Graph operators must filter to models in the final result (an ancestor that's a source/seed is not a
  selectable target, but ancestor traversal still passes through it to reach upstream models).
- Unknown name / no match → return `[]` (don't raise); the CLI surfaces "nothing selected".
- Deterministic, de-duplicated, sorted output.

## Verify

```bash
uv run pytest tests/test_selection.py
uv run ruff check . && uv run ruff format --check .
```

## Acceptance criteria

- [ ] `select_nodes(fx, None)` returns all 7 fixture model unique_ids.
- [ ] `select_nodes(fx, "customers")` → just `model.jaffle.customers`.
- [ ] `select_nodes(fx, "+customers")` includes `customers` and its model ancestors (`stg_customers`,
      `stg_orders`).
- [ ] `select_nodes(fx, "stg_orders+")` includes `stg_orders` and its descendants.
- [ ] `path:models/staging` returns only the staging models.
- [ ] Space = union, comma = intersection behave as specified; unknown name → `[]`.
