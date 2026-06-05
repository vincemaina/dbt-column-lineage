from pathlib import Path

from dbt_column_lineage.artifacts import ManifestNode, Relation, load_artifacts
from dbt_column_lineage.classify import build_model_edges
from dbt_column_lineage.control import extract_controls
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
