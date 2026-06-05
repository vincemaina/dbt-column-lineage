# Task 08 — Lineage graph + transitive traversal

**Review gate:** no · **Prerequisites:** tasks 01–02 (uses IR only) · **Status:** see [CHECKLIST](./CHECKLIST.md)

## Objective

Build a queryable graph over `LineageEdge`s and answer transitive `upstream` / `downstream` questions
for a column, cycle-safely. Pure IR in, pure IR out — no SQLGlot, no artifacts.

## Context

Read first: [`task-02-ir.md`](./task-02-ir.md) (`ColumnRef`, `LineageEdge`) and
[`../architecture.md`](../architecture.md) §4 ("Direct vs transitive").

## Files to create

```
src/dbt_column_lineage/graph.py
tests/test_graph.py
```
(Add `graph.py` to `src/dbt_column_lineage/CLAUDE.md`.)

## Required interface (implement exactly)

```python
def parse_column_ref(text: str) -> ColumnRef:
    """ 'model.jaffle.customers.lifetime_value' -> ColumnRef(asset='model.jaffle.customers',
        column='lifetime_value'). Split on the LAST dot (asset ids themselves contain dots).
        Column is lower-cased. Raise ValueError if there is no dot. """

class LineageGraph:
    def __init__(self, edges: Iterable[LineageEdge]) -> None: ...
    def upstream(self, ref: ColumnRef, *, transitive: bool = True) -> list[ColumnRef]: ...
    def downstream(self, ref: ColumnRef, *, transitive: bool = True) -> list[ColumnRef]: ...
    def edges_into(self, ref: ColumnRef) -> list[LineageEdge]:   # direct edges whose downstream == ref
    def edges_out_of(self, ref: ColumnRef) -> list[LineageEdge]: # direct edges whose upstream == ref
```

## Requirements

- Build adjacency maps keyed by `ColumnRef` (it's frozen/hashable) in both directions.
- `transitive=True` → full ancestor/descendant set via BFS/DFS with a `visited` set (cycle-safe; a
  malformed cyclic graph must not loop forever). `transitive=False` → one hop only.
- Results exclude the starting `ref` itself, are **de-duplicated**, and returned in a **deterministic
  order** (e.g. sorted by `str(ColumnRef)`).
- A `ref` with no edges returns `[]` (not an error).

## Verify

```bash
uv run pytest tests/test_graph.py
uv run ruff check . && uv run ruff format --check .
```

## Acceptance criteria

- [ ] On a hand-built multi-hop edge set, `upstream(transitive=True)` returns all ancestors and
      `transitive=False` returns only direct parents; same for `downstream`.
- [ ] A constructed cycle terminates and returns each node once.
- [ ] `parse_column_ref("model.jaffle.customers.lifetime_value")` returns the right split; a string with
      no dot raises `ValueError`.
- [ ] Ordering of results is deterministic across runs.
