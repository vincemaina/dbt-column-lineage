# Task 02 — Lineage IR data model

**Review gate:** YES (Opus must review before task 04+) · **Prerequisites:** task 01 · **Status:** see [CHECKLIST](./CHECKLIST.md)

## Objective

Define the immutable in-memory data model for column lineage — the contract every other module produces
or consumes. This is the most important interface in Phase 1; get the names/shapes exactly right.

## Context

Read first: [`../architecture.md`](../architecture.md) §4 (Intermediate representation). The enums and
fields below come from there. **Do not rename or add fields** beyond this spec without escalating.

The INDIRECT / control-lineage parts are **reserved**: the enum values exist, but no code in Phase 1
produces an INDIRECT edge. They must exist now so the model is stable when Phase 4 fills them in.

## Files to create

```
src/dbt_column_lineage/ir.py
tests/test_ir.py
```
(Also add `ir.py` to `src/dbt_column_lineage/CLAUDE.md`'s module list.)

## Required interface (implement exactly)

Use `enum.Enum` (str-valued) and frozen dataclasses. Public names must match exactly.

```python
class LineageType(str, Enum):
    DIRECT = "DIRECT"        # value lineage — output value derived from the input value
    INDIRECT = "INDIRECT"    # control lineage (join/filter/group/sort/window) — RESERVED, unused in Phase 1

class TransformCategory(str, Enum):
    IDENTITY = "IDENTITY"        # straight passthrough, same name
    RENAME = "RENAME"            # passthrough under a new name
    CAST = "CAST"                # type cast only
    EXPRESSION = "EXPRESSION"    # deterministic scalar expression
    AGGREGATION = "AGGREGATION"  # SUM/COUNT/etc.
    WINDOW = "WINDOW"            # window function
    CASE = "CASE"                # CASE expression
    COALESCE = "COALESCE"        # COALESCE/NVL/IFNULL
    UNION = "UNION"              # contributed via a set operation branch
    JOIN_DERIVED = "JOIN_DERIVED"# value comes from a joined relation (not the from-anchor)
    UNKNOWN = "UNKNOWN"          # could not classify

class ControlCategory(str, Enum):   # RESERVED for Phase 4 — defined now, unused now
    JOIN = "JOIN"
    FILTER = "FILTER"
    GROUP_BY = "GROUP_BY"
    SORT = "SORT"
    WINDOW_PARTITION = "WINDOW_PARTITION"
    CONDITIONAL = "CONDITIONAL"

class SchemaProvenance(str, Enum):
    CATALOG = "catalog"      # authoritative, from catalog.json
    INFERRED = "inferred"    # computed by parsing compiled SQL — RESERVED for Phase 2
    UNKNOWN = "unknown"      # could not resolve schema; degraded result

class Confidence(str, Enum):
    HIGH = "high"
    LOW = "low"

@dataclass(frozen=True)
class ColumnRef:
    asset: str    # dbt unique_id, e.g. "model.my_project.orders"
    column: str   # normalized (lower-cased) column name
    # implement __str__ -> f"{asset}.{column}"

@dataclass(frozen=True)
class SourceLocation:
    path: str | None        # original_file_path from manifest, if known
    asset: str | None       # owning dbt unique_id

@dataclass(frozen=True)
class LineageEdge:
    downstream: ColumnRef
    upstream: ColumnRef
    lineage_type: LineageType
    transform: TransformCategory                 # meaningful when lineage_type == DIRECT
    control: ControlCategory | None = None       # RESERVED; always None in Phase 1
    expression: str | None = None                # producing SQL text (from sqlglot)
    schema_provenance: SchemaProvenance = SchemaProvenance.UNKNOWN
    confidence: Confidence = Confidence.LOW
    warnings: tuple[str, ...] = ()
    dialect: str = "snowflake"
    source_location: SourceLocation | None = None

@dataclass(frozen=True)
class LineageResult:
    edges: tuple[LineageEdge, ...]
    # Models that were processed and any model-level warnings (e.g. parse failures).
    processed_assets: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
```

## Serialization

Provide pure functions (not methods that import json formatting concerns):

```python
def edge_to_dict(edge: LineageEdge) -> dict: ...
def result_to_dict(result: LineageResult) -> dict: ...
```

- Enums serialize to their `.value` strings.
- `ColumnRef` serializes to `{"asset": ..., "column": ...}`.
- Omit `None` optionals OR include them as `null` — **pick one and be consistent**; document the choice
  in the module docstring. (Recommended: include keys with `null` for a stable schema.)
- `warnings` → JSON array; empty tuple → `[]`.
- Output must be deterministic (stable key order) so JSON diffs are clean.

## Verify

```bash
uv run pytest tests/test_ir.py
uv run ruff check . && uv run ruff format --check .
```

## Acceptance criteria

- [ ] All enums and dataclasses exist with the exact public names and values above.
- [ ] Dataclasses are frozen (hashable); `ColumnRef.__str__` returns `"asset.column"`.
- [ ] `edge_to_dict` / `result_to_dict` produce deterministic, JSON-serializable dicts
      (`json.dumps(result_to_dict(r))` succeeds).
- [ ] Tests cover: enum values, frozen/hashable behaviour, `ColumnRef` str, round-trippable dict shape
      for a hand-built edge with and without optionals.
- [ ] No INDIRECT edge or `ControlCategory` value is produced anywhere — they exist but are unused.
- [ ] `ir.py` listed in `src/dbt_column_lineage/CLAUDE.md`.

## Open questions for Opus
_(Implementer: add here and stop if anything is unclear.)_
