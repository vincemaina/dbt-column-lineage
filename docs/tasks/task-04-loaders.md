# Task 04 — Artifact loaders (manifest / catalog)

**Review gate:** no · **Prerequisites:** tasks 01–03 · **Status:** see [CHECKLIST](./CHECKLIST.md)

## Objective

Load `manifest.json` + `catalog.json` into typed, engine-friendly objects. This is the only module that
knows the raw dbt-artifact JSON shape; everything downstream uses these types.

## Context

Read first: the **minimal consumed-artifact schema** in [`task-03-fixture.md`](./task-03-fixture.md)
(the exact fields to read) and [`../architecture.md`](../architecture.md) §3, §5. Only read the fields
listed there — ignore everything else in the JSON.

## Files to create

```
src/dbt_column_lineage/artifacts.py
tests/test_artifacts.py
```
(Add `artifacts.py` to `src/dbt_column_lineage/CLAUDE.md`.)

## Required interface (implement exactly)

```python
@dataclass(frozen=True)
class Relation:
    database: str
    schema: str
    name: str                     # model/seed alias, or source identifier
    def key(self) -> str:         # "DATABASE.SCHEMA.NAME", UPPER-cased (Snowflake unquoted folding)

@dataclass(frozen=True)
class ManifestNode:
    unique_id: str
    resource_type: str            # "model" | "seed" | "source"
    name: str
    relation: Relation
    compiled_code: str | None     # None for sources/seeds
    depends_on: tuple[str, ...]   # upstream unique_ids (empty for sources)
    original_file_path: str | None

@dataclass(frozen=True)
class CatalogColumn:
    name: str                     # as stored in catalog (UPPER for Snowflake)
    type: str
    index: int

@dataclass(frozen=True)
class CatalogEntry:
    unique_id: str
    relation: Relation
    columns: tuple[CatalogColumn, ...]

@dataclass(frozen=True)
class DbtArtifacts:
    nodes: dict[str, ManifestNode]          # models + seeds, by unique_id
    sources: dict[str, ManifestNode]        # sources, by unique_id
    parent_map: dict[str, tuple[str, ...]]
    child_map: dict[str, tuple[str, ...]]
    catalog: dict[str, CatalogEntry]        # by unique_id (models + sources)

    def get_node(self, unique_id: str) -> ManifestNode | None      # checks nodes then sources
    def models(self) -> list[ManifestNode]                          # resource_type == "model" with compiled_code
    def relation_to_uid(self) -> dict[str, str]                     # Relation.key() -> unique_id, across nodes+sources

def load_manifest(path: str | Path) -> tuple[dict[str, ManifestNode], dict[str, ManifestNode], dict, dict]
def load_catalog(path: str | Path) -> dict[str, CatalogEntry]
def load_artifacts(manifest_path: str | Path, catalog_path: str | Path) -> DbtArtifacts
```

## Requirements

- Relation name comes from `alias` for models/seeds (fall back to `name` if `alias` missing) and from
  `identifier` for sources (fall back to `name`).
- `Relation.key()` upper-cases — it is the join key between SQL table references, catalog, and manifest.
- `depends_on` from `node["depends_on"]["nodes"]` (default empty).
- `relation_to_uid()` spans models, seeds, **and** sources (so SQL table refs can be mapped to assets).
  If two relations collide on `key()`, keep the first and add nothing magic — just be deterministic.
- Be tolerant of missing optional fields (use `.get` with sensible defaults); raise a clear `ValueError`
  only if a required file is unreadable or not JSON.

## Verify

```bash
uv run pytest tests/test_artifacts.py
uv run ruff check . && uv run ruff format --check .
```

## Acceptance criteria

- [ ] `load_artifacts(fixture manifest, fixture catalog)` returns a `DbtArtifacts` with all 7 models in
      `.models()`, both sources in `.sources`, and catalog entries for every model + source.
- [ ] `relation_to_uid()` maps e.g. `"ANALYTICS.STAGING.STG_ORDERS"` → `"model.jaffle.stg_orders"` and
      `"RAW.JAFFLE.RAW_ORDERS"` → the source unique_id.
- [ ] `get_node("model.jaffle.customers").compiled_code` is the expected SQL; a source node has
      `compiled_code is None`.
- [ ] `parent_map`/`child_map` round-trip from the fixture.
- [ ] Tests use the task-03 fixture (not inline JSON) and cover the relation-name alias/identifier rules.
