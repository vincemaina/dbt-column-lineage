# Task 09 — Serializers (JSON + Mermaid)

**Review gate:** no · **Prerequisites:** tasks 01–02 (uses IR) · **Status:** see [CHECKLIST](./CHECKLIST.md)

## Objective

Render a `LineageResult` to the two Phase 1 output formats: the internal JSON contract and a Mermaid
diagram. Deterministic output so diffs are clean.

## Context

Read first: [`task-02-ir.md`](./task-02-ir.md) (`result_to_dict` already exists there — reuse it) and
[`../architecture.md`](../architecture.md) §6. OpenLineage export is **out of scope** (Phase 5).
If `vendor/` has the Canva extractor, its `visualization.py` is a Mermaid reference.

## Files to create

```
src/dbt_column_lineage/serialize.py
tests/test_serialize.py
```
(Add `serialize.py` to `src/dbt_column_lineage/CLAUDE.md`.)

## Required interface (implement exactly)

```python
def to_json(result: LineageResult, *, indent: int = 2) -> str:
    """ Deterministic JSON string. Built on ir.result_to_dict; stable key order. """

def write_json(result: LineageResult, path: str | Path, *, indent: int = 2) -> None:

def to_mermaid(result: LineageResult) -> str:
    """ Mermaid 'flowchart TD'. One node per distinct ColumnRef (id sanitized, label 'asset.column').
        One edge per LineageEdge, upstream --> downstream, labelled with the transform category. """
```

## Requirements

- `to_json` must round-trip through `json.loads` and be byte-stable for the same input (sort keys or use
  the IR's already-ordered dict; do not depend on set iteration order).
- Mermaid node ids must be valid (sanitize `.`/special chars to e.g. `_`); keep a deterministic mapping
  so the same `ColumnRef` always gets the same id. Labels show the human-readable `asset.column`.
- Edge label = `edge.transform.value` (e.g. `CAST`). Keep output deterministic (sort edges).
- No file I/O in `to_json`/`to_mermaid`; only `write_json` touches disk.

## Verify

```bash
uv run pytest tests/test_serialize.py
uv run ruff check . && uv run ruff format --check .
```

## Acceptance criteria

- [ ] `json.loads(to_json(result))` reproduces the dict from `result_to_dict`.
- [ ] `to_json` is identical across repeated calls / process runs for the same `LineageResult`.
- [ ] `to_mermaid` starts with `flowchart TD`, contains a node per distinct column and an edge per
      `LineageEdge` with the transform label; ids are sanitized and stable.
- [ ] `write_json` writes a file that parses back to the same structure.
