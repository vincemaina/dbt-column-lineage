"""Schema resolution: produce the relation -> {column: type} map the SQL adapter feeds to SQLGlot,
plus per-relation provenance. Phase 1 has only the authoritative CatalogSchemaResolver.

Pure: no SQLGlot import here (the adapter converts SchemaMapping into SQLGlot's structure).
"""

from typing import Protocol

from dbt_column_lineage.artifacts import DbtArtifacts
from dbt_column_lineage.ir import SchemaProvenance

# Relation.key() -> {column_name: sql_type}, both kept in catalog casing (UPPER for Snowflake).
SchemaMapping = dict[str, dict[str, str]]


class SchemaResolver(Protocol):
    def schema(self) -> SchemaMapping: ...

    def provenance(self, relation_key: str) -> SchemaProvenance: ...


class CatalogSchemaResolver:
    def __init__(self, artifacts: DbtArtifacts) -> None:
        self._artifacts = artifacts
        self._schema: SchemaMapping | None = None

    def schema(self) -> SchemaMapping:
        if self._schema is None:
            self._schema = {
                entry.relation.key(): {c.name: c.type for c in entry.columns}
                for entry in self._artifacts.catalog.values()
            }
        return self._schema

    def provenance(self, relation_key: str) -> SchemaProvenance:
        in_catalog = relation_key.upper() in self.schema()
        return SchemaProvenance.CATALOG if in_catalog else SchemaProvenance.UNKNOWN
