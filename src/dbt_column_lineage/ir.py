"""Lineage intermediate representation (IR) — the immutable data model for column lineage.

Each lineage edge carries an ordered CHAIN of transform steps (`transforms`) describing every
operation the value passes through from upstream column to downstream column — value operations
(cast, coalesce, aggregation, ...) and the structural `JOIN` it flows through. Each step records its
`kind` plus structured `detail` facts (join_type, func, default, from/to, ...). The engine records
facts only; it does not judge whether a guarantee (e.g. not_null) survives — that is a consumer's job.

Enums serialize to their `.value` strings. Dataclasses are frozen (immutable). `ColumnRef` is hashable
(used as a graph key); `LineageEdge`/`TransformStep` are immutable but not hashable (they carry a dict
`detail`). Serialized dicts include all fields, with None as null and empty collections as []/{}.
"""

from dataclasses import dataclass, field
from enum import Enum


class LineageType(str, Enum):
    DIRECT = "DIRECT"  # value lineage — output value derived from the input value
    INDIRECT = "INDIRECT"  # control lineage (join/filter/group keys) — RESERVED, unused in Phase 1


class TransformKind(str, Enum):
    """One operation in an edge's transform chain. JOIN is structural (how the value's relation
    enters the query); the rest are value/projection operations. UNION marks a set-operation branch."""

    IDENTITY = "IDENTITY"  # passthrough, same name
    RENAME = "RENAME"  # passthrough, new name
    CAST = "CAST"
    COALESCE = "COALESCE"
    CASE = "CASE"
    AGGREGATION = "AGGREGATION"
    WINDOW = "WINDOW"
    EXPRESSION = "EXPRESSION"  # other deterministic scalar expression
    UNION = "UNION"  # contributed via a set-operation branch
    JOIN = "JOIN"  # structural: value's relation entered via a join
    UNKNOWN = "UNKNOWN"


class ControlCategory(str, Enum):  # RESERVED for Phase 4 — defined now, unused now
    JOIN = "JOIN"
    FILTER = "FILTER"
    GROUP_BY = "GROUP_BY"
    SORT = "SORT"
    WINDOW_PARTITION = "WINDOW_PARTITION"
    CONDITIONAL = "CONDITIONAL"


class SchemaProvenance(str, Enum):
    CATALOG = "catalog"  # authoritative, from catalog.json
    INFERRED = "inferred"  # computed by parsing compiled SQL — RESERVED for Phase 2
    UNKNOWN = "unknown"  # could not resolve schema; degraded result


class Confidence(str, Enum):
    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True)
class ColumnRef:
    asset: str  # dbt unique_id, e.g. "model.my_project.orders"
    column: str  # normalized (lower-cased) column name

    def __str__(self) -> str:
        return f"{self.asset}.{self.column}"


@dataclass(frozen=True)
class SourceLocation:
    path: str | None  # original_file_path from manifest, if known
    asset: str | None  # owning dbt unique_id


@dataclass(frozen=True)
class TransformStep:
    """One operation in the transform chain, with structured facts in `detail`.

    Conventional `detail` keys by kind (all optional, facts only):
      RENAME      -> {"from": <src col>, "to": <out col>}
      CAST        -> {"to_type": "NUMBER(38, 2)"}
      COALESCE    -> {"default": "'unknown'"}
      AGGREGATION -> {"func": "COUNT"}
      WINDOW      -> {"func": "ROW_NUMBER", "role": "partition_by" | "order_by" | "value"}
      JOIN        -> {"join_type": "LEFT"|"RIGHT"|"INNER"|"FULL"|"CROSS", "introduces_nulls": bool}
      UNION       -> {"branch": 0}
      IDENTITY/CASE/EXPRESSION/UNKNOWN -> {} (or expression-specific facts)
    """

    kind: TransformKind
    detail: dict[str, str | int | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class LineageEdge:
    downstream: ColumnRef
    upstream: ColumnRef
    lineage_type: LineageType
    transforms: tuple[TransformStep, ...]  # ordered chain, upstream -> downstream
    control: ControlCategory | None = None  # RESERVED (Phase 4); always None in Phase 1
    expression: str | None = None  # full producing SQL text for the output column
    schema_provenance: SchemaProvenance = SchemaProvenance.UNKNOWN
    confidence: Confidence = Confidence.LOW
    warnings: tuple[str, ...] = ()
    dialect: str = "snowflake"
    source_location: SourceLocation | None = None


@dataclass(frozen=True)
class ColumnDiff:
    """Per-model schema reconciliation (hybrid mode): inferred (current code) vs catalog (built).
    `added`/`removed` = columns introduced/dropped; `retyped` = (column, old_type, new_type) where the
    inferred type (propagated from upstream catalog types) differs from the built catalog type."""

    asset: str
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    retyped: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True)
class ControlEdge:
    """A column that INFLUENCES a model's rows without flowing into a value — a join key, filter
    predicate, or group-by/sort column. Model-level: a filter affects all output columns, so these are
    recorded once per model, not per output column. Resolved to the base source column."""

    downstream_asset: str  # the model whose rows are influenced
    upstream: ColumnRef  # the base source column
    category: ControlCategory  # JOIN | FILTER | GROUP_BY | SORT


@dataclass(frozen=True)
class SelfReference:
    """An output column that reads its own model's prior state (incremental `{{ this }}`)."""

    asset: str
    column: str  # the output column
    references: str  # the column of the same model it reads


@dataclass(frozen=True)
class LineageResult:
    edges: tuple[LineageEdge, ...]
    processed_assets: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    reconciliation: tuple[ColumnDiff, ...] = ()  # populated only in hybrid mode
    controls: tuple[ControlEdge, ...] = ()  # control / INDIRECT lineage (model-level)
    self_references: tuple[SelfReference, ...] = ()  # incremental {{ this }} self-reads


def transform_label(transforms: tuple[TransformStep, ...]) -> str:
    """Human-readable summary of a chain, e.g. 'JOIN→RENAME'. For CLI/Mermaid display."""
    return "→".join(s.kind.value for s in transforms) or "UNKNOWN"


def step_to_dict(step: TransformStep) -> dict:
    return {"kind": step.kind.value, "detail": dict(step.detail)}


def edge_to_dict(edge: LineageEdge) -> dict:
    return {
        "downstream": {"asset": edge.downstream.asset, "column": edge.downstream.column},
        "upstream": {"asset": edge.upstream.asset, "column": edge.upstream.column},
        "lineage_type": edge.lineage_type.value,
        "transforms": [step_to_dict(s) for s in edge.transforms],
        "control": edge.control.value if edge.control is not None else None,
        "expression": edge.expression,
        "schema_provenance": edge.schema_provenance.value,
        "confidence": edge.confidence.value,
        "warnings": list(edge.warnings),
        "dialect": edge.dialect,
        "source_location": (
            {"path": edge.source_location.path, "asset": edge.source_location.asset}
            if edge.source_location is not None
            else None
        ),
    }


def diff_to_dict(diff: ColumnDiff) -> dict:
    return {
        "asset": diff.asset,
        "added": list(diff.added),
        "removed": list(diff.removed),
        "retyped": [{"column": c, "from": old, "to": new} for c, old, new in diff.retyped],
    }


def control_edge_to_dict(control: ControlEdge) -> dict:
    return {
        "downstream_asset": control.downstream_asset,
        "upstream": {"asset": control.upstream.asset, "column": control.upstream.column},
        "category": control.category.value,
    }


def self_reference_to_dict(ref: SelfReference) -> dict:
    return {"asset": ref.asset, "column": ref.column, "references": ref.references}


def result_to_dict(result: LineageResult) -> dict:
    return {
        "edges": [edge_to_dict(e) for e in result.edges],
        "processed_assets": list(result.processed_assets),
        "warnings": list(result.warnings),
        "reconciliation": [diff_to_dict(d) for d in result.reconciliation],
        "controls": [control_edge_to_dict(c) for c in result.controls],
        "self_references": [self_reference_to_dict(s) for s in result.self_references],
    }
