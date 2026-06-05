import json

import pytest

from dbt_column_lineage.ir import (
    ColumnRef,
    Confidence,
    ControlCategory,
    LineageEdge,
    LineageResult,
    LineageType,
    SchemaProvenance,
    SourceLocation,
    TransformKind,
    TransformStep,
    edge_to_dict,
    result_to_dict,
    step_to_dict,
    transform_label,
)


class TestEnums:
    def test_lineage_type_values(self):
        assert LineageType.DIRECT.value == "DIRECT"
        assert LineageType.INDIRECT.value == "INDIRECT"

    def test_transform_kind_values(self):
        assert {k.value for k in TransformKind} == {
            "IDENTITY",
            "RENAME",
            "CAST",
            "COALESCE",
            "CASE",
            "AGGREGATION",
            "WINDOW",
            "EXPRESSION",
            "UNION",
            "JOIN",
            "UNKNOWN",
        }

    def test_control_category_values(self):
        assert {k.value for k in ControlCategory} == {
            "JOIN",
            "FILTER",
            "GROUP_BY",
            "SORT",
            "WINDOW_PARTITION",
            "CONDITIONAL",
        }

    def test_schema_provenance_values(self):
        assert SchemaProvenance.CATALOG.value == "catalog"
        assert SchemaProvenance.INFERRED.value == "inferred"
        assert SchemaProvenance.UNKNOWN.value == "unknown"

    def test_confidence_values(self):
        assert Confidence.HIGH.value == "high"
        assert Confidence.LOW.value == "low"


class TestColumnRef:
    def test_str(self):
        ref = ColumnRef(asset="model.project.users", column="user_id")
        assert str(ref) == "model.project.users.user_id"

    def test_frozen(self):
        ref = ColumnRef(asset="model.project.users", column="user_id")
        with pytest.raises(AttributeError):
            ref.column = "x"  # type: ignore[misc]

    def test_hashable(self):
        a = ColumnRef("model.project.users", "user_id")
        b = ColumnRef("model.project.users", "user_id")
        assert len({a, b}) == 1


class TestTransformStep:
    def test_default_detail_is_empty(self):
        step = TransformStep(kind=TransformKind.IDENTITY)
        assert step.detail == {}

    def test_default_detail_not_shared(self):
        a = TransformStep(kind=TransformKind.IDENTITY)
        b = TransformStep(kind=TransformKind.IDENTITY)
        assert a.detail is not b.detail  # field(default_factory=dict)

    def test_detail_facts(self):
        step = TransformStep(TransformKind.JOIN, {"join_type": "LEFT", "introduces_nulls": True})
        assert step.detail["join_type"] == "LEFT"
        assert step.detail["introduces_nulls"] is True

    def test_step_to_dict(self):
        step = TransformStep(TransformKind.AGGREGATION, {"func": "COUNT"})
        assert step_to_dict(step) == {"kind": "AGGREGATION", "detail": {"func": "COUNT"}}


def _edge(**kw) -> LineageEdge:
    base = dict(
        downstream=ColumnRef("model.project.orders", "order_id"),
        upstream=ColumnRef("model.project.raw_orders", "id"),
        lineage_type=LineageType.DIRECT,
        transforms=(TransformStep(TransformKind.RENAME, {"from": "id", "to": "order_id"}),),
    )
    base.update(kw)
    return LineageEdge(**base)


class TestLineageEdge:
    def test_minimal_defaults(self):
        edge = _edge()
        assert edge.control is None
        assert edge.expression is None
        assert edge.schema_provenance == SchemaProvenance.UNKNOWN
        assert edge.confidence == Confidence.LOW
        assert edge.warnings == ()
        assert edge.dialect == "snowflake"
        assert edge.source_location is None

    def test_transform_chain(self):
        edge = _edge(
            transforms=(
                TransformStep(TransformKind.JOIN, {"join_type": "LEFT", "introduces_nulls": True}),
                TransformStep(
                    TransformKind.RENAME, {"from": "first_name", "to": "customer_first_name"}
                ),
            )
        )
        assert [s.kind for s in edge.transforms] == [TransformKind.JOIN, TransformKind.RENAME]

    def test_frozen(self):
        edge = _edge()
        with pytest.raises(AttributeError):
            edge.dialect = "bigquery"  # type: ignore[misc]

    def test_transform_label(self):
        edge = _edge(
            transforms=(
                TransformStep(TransformKind.JOIN, {"join_type": "LEFT"}),
                TransformStep(TransformKind.RENAME),
            )
        )
        assert transform_label(edge.transforms) == "JOIN→RENAME"
        assert transform_label(()) == "UNKNOWN"


class TestSerialization:
    def test_edge_to_dict_minimal(self):
        edge = _edge(transforms=(TransformStep(TransformKind.IDENTITY),))
        d = edge_to_dict(edge)
        assert d["downstream"] == {"asset": "model.project.orders", "column": "order_id"}
        assert d["upstream"] == {"asset": "model.project.raw_orders", "column": "id"}
        assert d["lineage_type"] == "DIRECT"
        assert d["transforms"] == [{"kind": "IDENTITY", "detail": {}}]
        assert d["control"] is None
        assert d["expression"] is None
        assert d["schema_provenance"] == "unknown"
        assert d["confidence"] == "low"
        assert d["warnings"] == []
        assert d["dialect"] == "snowflake"
        assert d["source_location"] is None

    def test_edge_to_dict_full_chain(self):
        edge = _edge(
            transforms=(
                TransformStep(TransformKind.JOIN, {"join_type": "LEFT", "introduces_nulls": True}),
                TransformStep(TransformKind.AGGREGATION, {"func": "COUNT"}),
            ),
            expression="count(o.order_id)",
            schema_provenance=SchemaProvenance.CATALOG,
            confidence=Confidence.HIGH,
            warnings=("w1",),
            source_location=SourceLocation(
                path="models/marts/customers.sql", asset="model.project.customers"
            ),
        )
        d = edge_to_dict(edge)
        assert d["transforms"] == [
            {"kind": "JOIN", "detail": {"join_type": "LEFT", "introduces_nulls": True}},
            {"kind": "AGGREGATION", "detail": {"func": "COUNT"}},
        ]
        assert d["schema_provenance"] == "catalog"
        assert d["confidence"] == "high"
        assert d["warnings"] == ["w1"]
        assert d["source_location"] == {
            "path": "models/marts/customers.sql",
            "asset": "model.project.customers",
        }

    def test_edge_to_dict_json_serializable(self):
        assert json.dumps(edge_to_dict(_edge())) is not None

    def test_result_to_dict(self):
        result = LineageResult(
            edges=(_edge(),),
            processed_assets=("model.project.orders",),
            warnings=("warn",),
        )
        d = result_to_dict(result)
        assert len(d["edges"]) == 1
        assert d["processed_assets"] == ["model.project.orders"]
        assert d["warnings"] == ["warn"]
        assert json.dumps(d) is not None

    def test_result_to_dict_empty(self):
        d = result_to_dict(LineageResult(edges=()))
        assert d == {"edges": [], "processed_assets": [], "warnings": [], "reconciliation": []}

    def test_deterministic_key_order(self):
        edge = _edge()
        assert list(edge_to_dict(edge).keys()) == list(edge_to_dict(edge).keys())
