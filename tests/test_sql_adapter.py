import inspect
from pathlib import Path

import pytest
from sqlglot import exp

from dbt_column_lineage.artifacts import load_artifacts
from dbt_column_lineage.schema_resolver import CatalogSchemaResolver
from dbt_column_lineage.sql_adapter import extract_column_lineage

FIXTURE = Path(__file__).parent / "fixtures" / "jaffle"


@pytest.fixture
def env():
    artifacts = load_artifacts(FIXTURE / "manifest.json", FIXTURE / "catalog.json")
    return artifacts, CatalogSchemaResolver(artifacts).schema()


def _one(artifacts, schema, uid, columns):
    node = artifacts.get_node(uid)
    return {
        rcl.output_column: rcl
        for rcl in extract_column_lineage(node.compiled_code, columns, schema)
    }


def test_rename_and_cast_sources(env):
    artifacts, schema = env
    res = _one(artifacts, schema, "model.jaffle.stg_orders", ["order_id", "amount"])
    order_id = res["order_id"].sources
    assert len(order_id) == 1
    assert order_id[0].relation_key == "RAW.JAFFLE.RAW_ORDERS"
    assert order_id[0].column == "ID"
    assert order_id[0].unresolved is False
    assert order_id[0].join is None
    # amount's projection is a Cast
    assert isinstance(res["amount"].sources[0].projection, exp.Cast)


def test_join_context_attached(env):
    artifacts, schema = env
    res = _one(artifacts, schema, "model.jaffle.customers", ["number_of_orders", "customer_id"])
    noo = res["number_of_orders"].sources[0]
    assert noo.relation_key == "ANALYTICS.STAGING.STG_ORDERS"
    assert noo.join == ("LEFT", True)  # left-joined, null-introducing
    cid = res["customer_id"].sources[0]
    assert cid.relation_key == "ANALYTICS.STAGING.STG_CUSTOMERS"
    assert cid.join is None  # from the FROM anchor


def test_star_expands_with_schema(env):
    artifacts, schema = env
    res = _one(
        artifacts,
        schema,
        "model.jaffle.star_passthrough",
        ["customer_id", "first_name", "last_name", "first_name_clean"],
    )
    fnc = res["first_name_clean"].sources
    assert len(fnc) == 1 and fnc[0].relation_key == "ANALYTICS.STAGING.STG_CUSTOMERS"
    assert fnc[0].unresolved is False


def test_set_operation_branches(env):
    artifacts, schema = env
    res = _one(artifacts, schema, "model.jaffle.all_names", ["name"])
    rcl = res["name"]
    assert rcl.is_set_operation is True
    by_branch = {s.branch_index: s.column for s in rcl.sources}
    assert by_branch == {0: "FIRST_NAME", 1: "LAST_NAME"}


def test_window_two_inputs(env):
    artifacts, schema = env
    res = _one(artifacts, schema, "model.jaffle.order_window", ["order_seq"])
    cols = {s.column for s in res["order_seq"].sources}
    assert cols == {"CUSTOMER_ID", "ORDERED_AT"}
    assert all(isinstance(s.projection, exp.Window) for s in res["order_seq"].sources)


def test_named_column_from_unexpandable_star_errors_gracefully():
    # asking for a named column when * can't expand: sqlglot errors -> warned, no fabricated source
    res = extract_column_lineage(
        "select * from ANALYTICS.STAGING.STG_CUSTOMERS", ["first_name"], schema={}
    )
    rcl = res[0]
    assert rcl.sources == ()
    assert any(w.startswith("parse_error") for w in rcl.warnings)


def test_star_leaf_marked_unresolved():
    # column resolving to a star from an un-schema'd subquery: relation known, column not -> unresolved
    res = extract_column_lineage("select a from (select * from RAW.X.T) s", ["a"], schema={})
    rcl = res[0]
    assert len(rcl.sources) == 1
    src = rcl.sources[0]
    assert src.relation_key == "RAW.X.T" and src.column == "*" and src.unresolved is True
    assert "select_star_unresolved" in rcl.warnings


def test_malformed_sql_is_contained():
    res = extract_column_lineage("this is not sql", ["x"], schema={})
    assert res[0].sources == ()
    assert any(w.startswith("parse_error") for w in res[0].warnings)


def test_only_adapter_and_classify_import_sqlglot():
    from dbt_column_lineage import artifacts as art_mod
    from dbt_column_lineage import schema_resolver as sr_mod

    assert "sqlglot" not in inspect.getsource(art_mod)
    assert "sqlglot" not in inspect.getsource(sr_mod)
