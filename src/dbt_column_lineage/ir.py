"""Lineage intermediate representation (IR) — the immutable data model for column lineage.

Enums serialize to their `.value` strings. Dataclasses are frozen (hashable). Dicts include all
fields including None optionals (for stable schema), with None serialized as null.
"""

from dataclasses import dataclass
from enum import Enum


class LineageType(str, Enum):
    DIRECT = "DIRECT"
    INDIRECT = "INDIRECT"


class TransformCategory(str, Enum):
    IDENTITY = "IDENTITY"
    RENAME = "RENAME"
    CAST = "CAST"
    EXPRESSION = "EXPRESSION"
    AGGREGATION = "AGGREGATION"
    WINDOW = "WINDOW"
    CASE = "CASE"
    COALESCE = "COALESCE"
    UNION = "UNION"
    JOIN_DERIVED = "JOIN_DERIVED"
    UNKNOWN = "UNKNOWN"


class ControlCategory(str, Enum):
    JOIN = "JOIN"
    FILTER = "FILTER"
    GROUP_BY = "GROUP_BY"
    SORT = "SORT"
    WINDOW_PARTITION = "WINDOW_PARTITION"
    CONDITIONAL = "CONDITIONAL"


class SchemaProvenance(str, Enum):
    CATALOG = "catalog"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class Confidence(str, Enum):
    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True)
class ColumnRef:
    asset: str
    column: str

    def __str__(self) -> str:
        return f"{self.asset}.{self.column}"


@dataclass(frozen=True)
class SourceLocation:
    path: str | None
    asset: str | None


@dataclass(frozen=True)
class LineageEdge:
    downstream: ColumnRef
    upstream: ColumnRef
    lineage_type: LineageType
    transform: TransformCategory
    control: ControlCategory | None = None
    expression: str | None = None
    schema_provenance: SchemaProvenance = SchemaProvenance.UNKNOWN
    confidence: Confidence = Confidence.LOW
    warnings: tuple[str, ...] = ()
    dialect: str = "snowflake"
    source_location: SourceLocation | None = None


@dataclass(frozen=True)
class LineageResult:
    edges: tuple[LineageEdge, ...]
    processed_assets: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def edge_to_dict(edge: LineageEdge) -> dict:
    return {
        "downstream": {
            "asset": edge.downstream.asset,
            "column": edge.downstream.column,
        },
        "upstream": {
            "asset": edge.upstream.asset,
            "column": edge.upstream.column,
        },
        "lineage_type": edge.lineage_type.value,
        "transform": edge.transform.value,
        "control": edge.control.value if edge.control is not None else None,
        "expression": edge.expression,
        "schema_provenance": edge.schema_provenance.value,
        "confidence": edge.confidence.value,
        "warnings": list(edge.warnings),
        "dialect": edge.dialect,
        "source_location": (
            {
                "path": edge.source_location.path,
                "asset": edge.source_location.asset,
            }
            if edge.source_location is not None
            else None
        ),
    }


def result_to_dict(result: LineageResult) -> dict:
    return {
        "edges": [edge_to_dict(e) for e in result.edges],
        "processed_assets": list(result.processed_assets),
        "warnings": list(result.warnings),
    }
