"""Load dbt artifacts (manifest.json + catalog.json) into typed, engine-friendly objects.

This is the only module that knows the raw dbt-artifact JSON shape. Only the minimal consumed-field
subset is read (see docs/tasks/task-03-fixture.md); everything else in the JSON is ignored.
"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Relation:
    database: str
    schema: str
    name: str  # model/seed alias, or source identifier

    def key(self) -> str:
        """Join key between SQL table refs, catalog, and manifest. Snowflake folds unquoted
        identifiers to upper case, so the key is upper-cased."""
        return f"{self.database}.{self.schema}.{self.name}".upper()


@dataclass(frozen=True)
class ManifestNode:
    unique_id: str
    resource_type: str  # "model" | "seed" | "source"
    name: str
    relation: Relation
    compiled_code: str | None  # None for sources/seeds
    depends_on: tuple[str, ...]
    original_file_path: str | None


@dataclass(frozen=True)
class CatalogColumn:
    name: str  # as stored in catalog (UPPER for Snowflake)
    type: str
    index: int


@dataclass(frozen=True)
class CatalogEntry:
    unique_id: str
    relation: Relation
    columns: tuple[CatalogColumn, ...]


@dataclass(frozen=True)
class DbtArtifacts:
    nodes: dict[str, ManifestNode]  # models + seeds, by unique_id
    sources: dict[str, ManifestNode]  # sources, by unique_id
    parent_map: dict[str, tuple[str, ...]]
    child_map: dict[str, tuple[str, ...]]
    catalog: dict[str, CatalogEntry]  # by unique_id (models + sources)

    def get_node(self, unique_id: str) -> ManifestNode | None:
        return self.nodes.get(unique_id) or self.sources.get(unique_id)

    def models(self) -> list[ManifestNode]:
        return [n for n in self.nodes.values() if n.resource_type == "model" and n.compiled_code]

    def relation_to_uid(self) -> dict[str, str]:
        """Relation.key() -> unique_id across nodes + sources (first wins on collision)."""
        out: dict[str, str] = {}
        for uid, node in {**self.nodes, **self.sources}.items():
            out.setdefault(node.relation.key(), uid)
        return out


def _read_json(path: str | Path) -> dict:
    p = Path(path)
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"Could not read JSON artifact {path}: {e}") from e


def _manifest_relation(raw: dict) -> Relation:
    # models/seeds use `alias`, sources use `identifier`; both fall back to `name`.
    name = raw.get("alias") or raw.get("identifier") or raw["name"]
    return Relation(raw["database"], raw["schema"], name)


def _manifest_node(uid: str, raw: dict, *, default_type: str, has_sql: bool) -> ManifestNode:
    return ManifestNode(
        unique_id=raw.get("unique_id", uid),
        resource_type=raw.get("resource_type", default_type),
        name=raw["name"],
        relation=_manifest_relation(raw),
        compiled_code=raw.get("compiled_code") if has_sql else None,
        depends_on=tuple(raw.get("depends_on", {}).get("nodes", [])),
        original_file_path=raw.get("original_file_path"),
    )


def load_manifest(
    path: str | Path,
) -> tuple[
    dict[str, ManifestNode],
    dict[str, ManifestNode],
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
]:
    data = _read_json(path)
    nodes = {
        uid: _manifest_node(uid, raw, default_type="model", has_sql=True)
        for uid, raw in data.get("nodes", {}).items()
    }
    sources = {
        uid: _manifest_node(uid, raw, default_type="source", has_sql=False)
        for uid, raw in data.get("sources", {}).items()
    }
    parent_map = {k: tuple(v) for k, v in data.get("parent_map", {}).items()}
    child_map = {k: tuple(v) for k, v in data.get("child_map", {}).items()}
    return nodes, sources, parent_map, child_map


def load_catalog(path: str | Path) -> dict[str, CatalogEntry]:
    data = _read_json(path)
    out: dict[str, CatalogEntry] = {}
    for uid, raw in {**data.get("nodes", {}), **data.get("sources", {})}.items():
        m = raw["metadata"]
        columns = tuple(
            CatalogColumn(
                name=c.get("name", cname), type=c.get("type", ""), index=c.get("index", i)
            )
            for i, (cname, c) in enumerate(raw.get("columns", {}).items(), start=1)
        )
        out[uid] = CatalogEntry(uid, Relation(m["database"], m["schema"], m["name"]), columns)
    return out


def load_artifacts(manifest_path: str | Path, catalog_path: str | Path) -> DbtArtifacts:
    nodes, sources, parent_map, child_map = load_manifest(manifest_path)
    return DbtArtifacts(nodes, sources, parent_map, child_map, load_catalog(catalog_path))
