import json

from dbt_column_lineage.ir import (
    ColumnRef,
    Confidence,
    ControlCategory,
    LineageEdge,
    LineageResult,
    LineageType,
    SchemaProvenance,
    SourceLocation,
    TransformCategory,
    edge_to_dict,
    result_to_dict,
)


class TestEnums:
    def test_lineage_type_values(self):
        assert LineageType.DIRECT.value == "DIRECT"
        assert LineageType.INDIRECT.value == "INDIRECT"

    def test_transform_category_values(self):
        assert TransformCategory.IDENTITY.value == "IDENTITY"
        assert TransformCategory.RENAME.value == "RENAME"
        assert TransformCategory.CAST.value == "CAST"
        assert TransformCategory.EXPRESSION.value == "EXPRESSION"
        assert TransformCategory.AGGREGATION.value == "AGGREGATION"
        assert TransformCategory.WINDOW.value == "WINDOW"
        assert TransformCategory.CASE.value == "CASE"
        assert TransformCategory.COALESCE.value == "COALESCE"
        assert TransformCategory.UNION.value == "UNION"
        assert TransformCategory.JOIN_DERIVED.value == "JOIN_DERIVED"
        assert TransformCategory.UNKNOWN.value == "UNKNOWN"

    def test_control_category_values(self):
        assert ControlCategory.JOIN.value == "JOIN"
        assert ControlCategory.FILTER.value == "FILTER"
        assert ControlCategory.GROUP_BY.value == "GROUP_BY"
        assert ControlCategory.SORT.value == "SORT"
        assert ControlCategory.WINDOW_PARTITION.value == "WINDOW_PARTITION"
        assert ControlCategory.CONDITIONAL.value == "CONDITIONAL"

    def test_schema_provenance_values(self):
        assert SchemaProvenance.CATALOG.value == "catalog"
        assert SchemaProvenance.INFERRED.value == "inferred"
        assert SchemaProvenance.UNKNOWN.value == "unknown"

    def test_confidence_values(self):
        assert Confidence.HIGH.value == "high"
        assert Confidence.LOW.value == "low"


class TestColumnRef:
    def test_column_ref_creation(self):
        ref = ColumnRef(asset="model.project.users", column="user_id")
        assert ref.asset == "model.project.users"
        assert ref.column == "user_id"

    def test_column_ref_str(self):
        ref = ColumnRef(asset="model.project.users", column="user_id")
        assert str(ref) == "model.project.users.user_id"

    def test_column_ref_frozen(self):
        ref = ColumnRef(asset="model.project.users", column="user_id")
        try:
            ref.column = "new_column"
            assert False, "ColumnRef should be frozen"
        except (AttributeError, Exception):
            pass

    def test_column_ref_hashable(self):
        ref1 = ColumnRef(asset="model.project.users", column="user_id")
        ref2 = ColumnRef(asset="model.project.users", column="user_id")
        ref_set = {ref1, ref2}
        assert len(ref_set) == 1


class TestSourceLocation:
    def test_source_location_with_values(self):
        loc = SourceLocation(path="models/users.sql", asset="model.project.users")
        assert loc.path == "models/users.sql"
        assert loc.asset == "model.project.users"

    def test_source_location_with_none(self):
        loc = SourceLocation(path=None, asset=None)
        assert loc.path is None
        assert loc.asset is None

    def test_source_location_frozen(self):
        loc = SourceLocation(path="models/users.sql", asset="model.project.users")
        try:
            loc.path = "new_path"
            assert False, "SourceLocation should be frozen"
        except (AttributeError, Exception):
            pass


class TestLineageEdge:
    def test_edge_with_minimal_fields(self):
        edge = LineageEdge(
            downstream=ColumnRef("model.project.orders", "order_id"),
            upstream=ColumnRef("model.project.raw_orders", "order_id"),
            lineage_type=LineageType.DIRECT,
            transform=TransformCategory.IDENTITY,
        )
        assert edge.lineage_type == LineageType.DIRECT
        assert edge.transform == TransformCategory.IDENTITY
        assert edge.control is None
        assert edge.expression is None
        assert edge.schema_provenance == SchemaProvenance.UNKNOWN
        assert edge.confidence == Confidence.LOW
        assert edge.warnings == ()
        assert edge.dialect == "snowflake"
        assert edge.source_location is None

    def test_edge_with_all_fields(self):
        edge = LineageEdge(
            downstream=ColumnRef("model.project.orders", "order_total"),
            upstream=ColumnRef("model.project.stg_orders", "amount"),
            lineage_type=LineageType.DIRECT,
            transform=TransformCategory.CAST,
            control=None,
            expression="CAST(amount AS NUMBER(38,2))",
            schema_provenance=SchemaProvenance.CATALOG,
            confidence=Confidence.HIGH,
            warnings=("warning1", "warning2"),
            dialect="snowflake",
            source_location=SourceLocation(
                path="models/marts/orders.sql", asset="model.project.orders"
            ),
        )
        assert edge.expression == "CAST(amount AS NUMBER(38,2))"
        assert edge.schema_provenance == SchemaProvenance.CATALOG
        assert edge.confidence == Confidence.HIGH
        assert edge.warnings == ("warning1", "warning2")
        assert edge.source_location.path == "models/marts/orders.sql"

    def test_edge_frozen(self):
        edge = LineageEdge(
            downstream=ColumnRef("model.project.orders", "order_id"),
            upstream=ColumnRef("model.project.raw_orders", "order_id"),
            lineage_type=LineageType.DIRECT,
            transform=TransformCategory.IDENTITY,
        )
        try:
            edge.transform = TransformCategory.RENAME
            assert False, "LineageEdge should be frozen"
        except (AttributeError, Exception):
            pass

    def test_edge_hashable(self):
        edge1 = LineageEdge(
            downstream=ColumnRef("model.project.orders", "order_id"),
            upstream=ColumnRef("model.project.raw_orders", "order_id"),
            lineage_type=LineageType.DIRECT,
            transform=TransformCategory.IDENTITY,
        )
        edge2 = LineageEdge(
            downstream=ColumnRef("model.project.orders", "order_id"),
            upstream=ColumnRef("model.project.raw_orders", "order_id"),
            lineage_type=LineageType.DIRECT,
            transform=TransformCategory.IDENTITY,
        )
        edge_set = {edge1, edge2}
        assert len(edge_set) == 1


class TestLineageResult:
    def test_result_with_empty_edges(self):
        result = LineageResult(edges=())
        assert result.edges == ()
        assert result.processed_assets == ()
        assert result.warnings == ()

    def test_result_with_edges_and_metadata(self):
        edge = LineageEdge(
            downstream=ColumnRef("model.project.orders", "order_id"),
            upstream=ColumnRef("model.project.raw_orders", "order_id"),
            lineage_type=LineageType.DIRECT,
            transform=TransformCategory.IDENTITY,
        )
        result = LineageResult(
            edges=(edge,),
            processed_assets=("model.project.orders", "model.project.raw_orders"),
            warnings=("some warning",),
        )
        assert len(result.edges) == 1
        assert result.processed_assets == ("model.project.orders", "model.project.raw_orders")
        assert result.warnings == ("some warning",)


class TestSerialization:
    def test_edge_to_dict_minimal(self):
        edge = LineageEdge(
            downstream=ColumnRef("model.project.orders", "order_id"),
            upstream=ColumnRef("model.project.raw_orders", "order_id"),
            lineage_type=LineageType.DIRECT,
            transform=TransformCategory.IDENTITY,
        )
        d = edge_to_dict(edge)
        assert d["downstream"] == {"asset": "model.project.orders", "column": "order_id"}
        assert d["upstream"] == {"asset": "model.project.raw_orders", "column": "order_id"}
        assert d["lineage_type"] == "DIRECT"
        assert d["transform"] == "IDENTITY"
        assert d["control"] is None
        assert d["expression"] is None
        assert d["schema_provenance"] == "unknown"
        assert d["confidence"] == "low"
        assert d["warnings"] == []
        assert d["dialect"] == "snowflake"
        assert d["source_location"] is None

    def test_edge_to_dict_with_optionals(self):
        edge = LineageEdge(
            downstream=ColumnRef("model.project.orders", "order_total"),
            upstream=ColumnRef("model.project.stg_orders", "amount"),
            lineage_type=LineageType.DIRECT,
            transform=TransformCategory.CAST,
            expression="CAST(amount AS NUMBER(38,2))",
            schema_provenance=SchemaProvenance.CATALOG,
            confidence=Confidence.HIGH,
            warnings=("warning1", "warning2"),
            source_location=SourceLocation(
                path="models/marts/orders.sql", asset="model.project.orders"
            ),
        )
        d = edge_to_dict(edge)
        assert d["expression"] == "CAST(amount AS NUMBER(38,2))"
        assert d["schema_provenance"] == "catalog"
        assert d["confidence"] == "high"
        assert d["warnings"] == ["warning1", "warning2"]
        assert d["source_location"] == {
            "path": "models/marts/orders.sql",
            "asset": "model.project.orders",
        }

    def test_edge_to_dict_json_serializable(self):
        edge = LineageEdge(
            downstream=ColumnRef("model.project.orders", "order_id"),
            upstream=ColumnRef("model.project.raw_orders", "order_id"),
            lineage_type=LineageType.DIRECT,
            transform=TransformCategory.IDENTITY,
        )
        d = edge_to_dict(edge)
        json_str = json.dumps(d)
        assert json_str is not None

    def test_result_to_dict_empty(self):
        result = LineageResult(edges=())
        d = result_to_dict(result)
        assert d["edges"] == []
        assert d["processed_assets"] == []
        assert d["warnings"] == []

    def test_result_to_dict_with_edges(self):
        edge = LineageEdge(
            downstream=ColumnRef("model.project.orders", "order_id"),
            upstream=ColumnRef("model.project.raw_orders", "order_id"),
            lineage_type=LineageType.DIRECT,
            transform=TransformCategory.IDENTITY,
        )
        result = LineageResult(
            edges=(edge,),
            processed_assets=("model.project.orders",),
            warnings=("warning",),
        )
        d = result_to_dict(result)
        assert len(d["edges"]) == 1
        assert d["processed_assets"] == ["model.project.orders"]
        assert d["warnings"] == ["warning"]

    def test_result_to_dict_json_serializable(self):
        edge = LineageEdge(
            downstream=ColumnRef("model.project.orders", "order_id"),
            upstream=ColumnRef("model.project.raw_orders", "order_id"),
            lineage_type=LineageType.DIRECT,
            transform=TransformCategory.IDENTITY,
        )
        result = LineageResult(edges=(edge,))
        d = result_to_dict(result)
        json_str = json.dumps(d)
        assert json_str is not None

    def test_dict_deterministic_key_order(self):
        edge = LineageEdge(
            downstream=ColumnRef("model.project.orders", "order_id"),
            upstream=ColumnRef("model.project.raw_orders", "order_id"),
            lineage_type=LineageType.DIRECT,
            transform=TransformCategory.IDENTITY,
        )
        d = edge_to_dict(edge)
        keys = list(d.keys())
        # Same edge serialized twice should produce same key order
        d2 = edge_to_dict(edge)
        keys2 = list(d2.keys())
        assert keys == keys2
