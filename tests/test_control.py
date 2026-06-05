from pathlib import Path

from dbt_column_lineage.artifacts import ManifestNode, Relation, load_artifacts
from dbt_column_lineage.classify import build_model_edges
from dbt_column_lineage.control import extract_controls, extract_operations, reads_from_stage
from dbt_column_lineage.engine import extract_lineage
from dbt_column_lineage.ir import ControlCategory, LineageType, SchemaProvenance, result_to_dict
from dbt_column_lineage.schema_resolver import CatalogSchemaResolver
from dbt_column_lineage.sql_adapter import build_sqlglot_schema, extract_column_lineage

FIXTURE = Path(__file__).parent / "fixtures" / "jaffle"
MANIFEST = FIXTURE / "manifest.json"
CATALOG = FIXTURE / "catalog.json"

SCHEMA = {"DB.S.A": {"ID": "NUMBER", "AMT": "NUMBER"}, "DB.S.B": {"CID": "NUMBER"}}
SQL = (
    "with c as (select id as cid, amt from DB.S.A where amt > 0) "
    "select c.cid, sum(c.amt) as t from c left join DB.S.B b on c.cid = b.cid "
    "where c.cid > 10 group by c.cid"
)


def _by_category(controls):
    out: dict = {}
    for rc in controls:
        out.setdefault(rc.category, set()).add((rc.relation_key, rc.column))
    return out


def test_filter_resolved_through_cte():
    cats = _by_category(extract_controls(SQL, SCHEMA))
    # `where amt > 0` inside the CTE, and `where c.cid > 10` outside (c.cid -> A.id)
    assert ("DB.S.A", "AMT") in cats[ControlCategory.FILTER]
    assert ("DB.S.A", "ID") in cats[ControlCategory.FILTER]


def test_join_keys_resolved_to_base():
    cats = _by_category(extract_controls(SQL, SCHEMA))
    assert cats[ControlCategory.JOIN] == {("DB.S.A", "ID"), ("DB.S.B", "CID")}


def test_group_by_resolved_to_base():
    cats = _by_category(extract_controls(SQL, SCHEMA))
    assert ("DB.S.A", "ID") in cats[ControlCategory.GROUP_BY]


def test_controls_on_fixture_with_positional_group_by():
    artifacts = load_artifacts(MANIFEST, CATALOG)
    schema = CatalogSchemaResolver(artifacts).schema()
    node = artifacts.get_node("model.jaffle.customers")
    cats = _by_category(extract_controls(node.compiled_code, schema))
    assert ("ANALYTICS.STAGING.STG_CUSTOMERS", "CUSTOMER_ID") in cats[ControlCategory.JOIN]
    assert ("ANALYTICS.STAGING.STG_ORDERS", "CUSTOMER_ID") in cats[ControlCategory.JOIN]
    # `group by 1, 2` (positional) -> customer_id, first_name
    assert ("ANALYTICS.STAGING.STG_CUSTOMERS", "CUSTOMER_ID") in cats[ControlCategory.GROUP_BY]
    assert ("ANALYTICS.STAGING.STG_CUSTOMERS", "FIRST_NAME") in cats[ControlCategory.GROUP_BY]


def test_engine_surfaces_controls():
    result = extract_lineage(MANIFEST, CATALOG)
    cats = {
        (c.category, c.upstream.asset, c.upstream.column)
        for c in result.controls
        if c.downstream_asset == "model.jaffle.customers"
    }
    assert (ControlCategory.JOIN, "model.jaffle.stg_orders", "customer_id") in cats
    assert (ControlCategory.GROUP_BY, "model.jaffle.stg_customers", "first_name") in cats
    assert "controls" in result_to_dict(result)


class _Resolver:
    def schema(self):
        return {}

    def provenance(self, relation_key):
        return SchemaProvenance.CATALOG


def test_self_reference_captured_not_dropped():
    # a model that reads from its own relation (incremental {{ this }})
    node = ManifestNode(
        unique_id="model.pkg.acc",
        resource_type="model",
        name="acc",
        relation=Relation("DB", "S", "ACC"),
        compiled_code="select id, ts from DB.S.ACC",
        depends_on=(),
        original_file_path=None,
    )
    schema = build_sqlglot_schema({"DB.S.ACC": {"ID": "NUMBER", "TS": "NUMBER"}})
    raw = extract_column_lineage(node.compiled_code, ["id", "ts"], schema)
    edges, _warnings, self_refs = build_model_edges(
        node, raw, {"DB.S.ACC": "model.pkg.acc"}, _Resolver()
    )
    assert edges == []  # self-edges are not value lineage
    pairs = {(s.column, s.references) for s in self_refs}
    assert pairs == {("id", "id"), ("ts", "ts")}


def test_operations_outer_join_groups_and_multiplies():
    ops = extract_operations(
        "select c.id, count(*) as n from a c left join b on c.id = b.id group by c.id"
    )
    assert ops.joins == ("LEFT",)
    assert ops.grouped is True
    assert ops.distinct is False
    assert ops.may_introduce_nulls is True  # LEFT join
    assert ops.may_multiply_rows is True  # a join is present


def test_operations_union_all_multiplies_without_nulls():
    ops = extract_operations("select a from t union all select a from u")
    assert ops.set_operation == "UNION ALL"
    assert ops.may_multiply_rows is True
    assert ops.may_introduce_nulls is False
    # plain UNION (dedup) is labelled but does not flag row multiplication on its own
    assert extract_operations("select a from t union select a from u").set_operation == "UNION"


def test_operations_lateral_flatten_multiplies():
    ops = extract_operations(
        "select f.value from t, lateral flatten(input => t.arr) f", dialect="snowflake"
    )
    assert ops.lateral_flatten is True
    assert ops.may_multiply_rows is True


def test_group_by_all_expands_to_non_aggregate_keys():
    # `GROUP BY ALL` -> group keys are a, b (the non-aggregate selects); count(*) is not a key
    cats = _by_category(
        extract_controls(
            "select a, b, count(*) c from DB.S.T group by all",
            {"DB.S.T": {"A": "NUMBER", "B": "NUMBER"}},
        )
    )
    assert cats[ControlCategory.GROUP_BY] == {("DB.S.T", "A"), ("DB.S.T", "B")}


def test_reads_from_stage_detection():
    assert reads_from_stage("select $1 as v from @lyst.db.my_stage") is True
    assert reads_from_stage("select a from DB.S.T") is False
    assert reads_from_stage("select email from DB.S.T where x = '@home'") is False  # @ only in literal


def test_operations_grain_maps_group_by_to_output_columns():
    # positional group by -> output column names; the grain is a unique key of the output rows
    assert extract_operations("select a, b, count(*) c from DB.S.T group by 1, 2").grain == ("a", "b")
    # group-by key selected under an alias -> the OUTPUT name
    assert extract_operations("select a as k, sum(x) s from DB.S.T group by a").grain == ("k",)
    # a grouped key that isn't selected -> no clean output grain key
    assert extract_operations("select sum(x) s from DB.S.T group by a").grain == ()
    assert extract_operations("select a, b from DB.S.T").grain == ()


def test_operations_plain_passthrough_is_inert():
    ops = extract_operations("select id, amt from DB.S.T")
    assert ops.joins == ()
    assert ops.set_operation is None
    assert (ops.grouped, ops.distinct, ops.lateral_flatten) == (False, False, False)
    assert ops.may_multiply_rows is False
    assert ops.may_introduce_nulls is False


def test_operations_unparseable_returns_none():
    assert extract_operations("select * from") is None


def test_engine_surfaces_operations():
    result = extract_lineage(MANIFEST, CATALOG)
    by_asset = {o.asset: o for o in result.operations}
    # customers: LEFT join + group by -> multiplies + nullable
    cust = by_asset["model.jaffle.customers"]
    assert cust.grouped is True and "LEFT" in cust.joins
    assert cust.may_introduce_nulls is True
    # all_names is a UNION ALL
    assert by_asset["model.jaffle.all_names"].set_operation == "UNION ALL"
    assert "operations" in result_to_dict(result)


def test_window_partition_order_are_indirect():
    # row_number()'s order_seq has no value input — its partition/order keys are control (INDIRECT)
    result = extract_lineage(MANIFEST, CATALOG, select="order_window")
    order_seq = [e for e in result.edges if e.downstream.column == "order_seq"]
    assert order_seq
    assert all(e.lineage_type == LineageType.INDIRECT for e in order_seq)
    assert all(e.control == ControlCategory.WINDOW_PARTITION for e in order_seq)


def test_case_condition_indirect_value_direct():
    # f's value comes from `amt` (THEN) = DIRECT; `flag` is the WHEN condition = INDIRECT/CONDITIONAL
    node = ManifestNode(
        unique_id="model.pkg.f",
        resource_type="model",
        name="f",
        relation=Relation("DB", "S", "F"),
        compiled_code="select case when flag = 1 then amt else 0 end as f from DB.S.A",
        depends_on=(),
        original_file_path=None,
    )
    schema = build_sqlglot_schema({"DB.S.A": {"FLAG": "NUMBER", "AMT": "NUMBER"}})
    raw = extract_column_lineage(node.compiled_code, ["f"], schema)
    edges, _w, _s = build_model_edges(node, raw, {"DB.S.A": "model.pkg.a"}, _Resolver())
    by_col = {e.upstream.column: e for e in edges}
    assert by_col["flag"].lineage_type == LineageType.INDIRECT
    assert by_col["flag"].control == ControlCategory.CONDITIONAL
    assert by_col["amt"].lineage_type == LineageType.DIRECT
