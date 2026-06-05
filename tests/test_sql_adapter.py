import inspect
from pathlib import Path

import pytest
from sqlglot import exp

from dbt_column_lineage.artifacts import load_artifacts
from dbt_column_lineage.classify import build_transform_chain
from dbt_column_lineage.ir import TransformKind
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
    assert order_id[0].join is None
    # amount's single hop is a Cast projection
    assert isinstance(res["amount"].sources[0].hops[-1].this, exp.Cast)


def test_join_context_attached(env):
    artifacts, schema = env
    res = _one(artifacts, schema, "model.jaffle.customers", ["number_of_orders", "customer_id"])
    assert res["number_of_orders"].sources[0].join == (
        "LEFT",
        True,
    )  # left-joined, null-introducing
    assert res["customer_id"].sources[0].join is None  # FROM anchor


def test_star_expands_with_schema(env):
    artifacts, schema = env
    res = _one(artifacts, schema, "model.jaffle.star_passthrough", ["first_name_clean"])
    fnc = res["first_name_clean"].sources
    assert len(fnc) == 1 and fnc[0].relation_key == "ANALYTICS.STAGING.STG_CUSTOMERS"


def test_set_operation_branches(env):
    artifacts, schema = env
    rcl = _one(artifacts, schema, "model.jaffle.all_names", ["name"])["name"]
    assert rcl.is_set_operation is True
    assert {s.branch_index: s.column for s in rcl.sources} == {0: "FIRST_NAME", 1: "LAST_NAME"}


def test_window_two_inputs(env):
    artifacts, schema = env
    res = _one(artifacts, schema, "model.jaffle.order_window", ["order_seq"])
    assert {s.column for s in res["order_seq"].sources} == {"CUSTOMER_ID", "ORDERED_AT"}
    assert all(isinstance(s.hops[-1].this, exp.Window) for s in res["order_seq"].sources)


def test_multi_hop_cte_chain():
    """A column transformed across CTE layers yields hops spanning both, and the chain is ordered
    source->output (inner CAST then outer SUM) — the core CTE fix."""
    sql = "with c as (select cast(x as int) as y from DB.S.T) select sum(y) as z from c"
    rcl = extract_column_lineage(sql, ["z"], {"DB.S.T": {"X": "NUMBER"}})[0]
    src = rcl.sources[0]
    assert src.relation_key == "DB.S.T" and src.column == "X"
    assert len(src.hops) == 2  # inner CTE hop + outer hop
    chain = [s.kind for s in build_transform_chain(src, "z")]
    assert chain == [TransformKind.CAST, TransformKind.AGGREGATION]


def test_cte_rename_threads_across_hops():
    """A rename inside a CTE must not break name-matching at the outer hop (the bug found on real data)."""
    sql = "with c as (select amt as renamed from DB.S.T) select sum(renamed) as total from c"
    rcl = extract_column_lineage(sql, ["total"], {"DB.S.T": {"AMT": "NUMBER"}})[0]
    chain = [s.kind for s in build_transform_chain(rcl.sources[0], "total")]
    assert TransformKind.UNKNOWN not in chain
    assert chain == [TransformKind.RENAME, TransformKind.AGGREGATION]


def test_named_column_from_unexpandable_star_errors_gracefully():
    # no schema -> * can't expand -> the named column is unresolvable: warned, no fabricated source
    res = extract_column_lineage(
        "select * from ANALYTICS.STAGING.STG_CUSTOMERS", ["first_name"], schema={}
    )
    assert res[0].sources == ()
    assert "unresolved_column" in res[0].warnings


def test_star_leaf_marked_unresolved():
    res = extract_column_lineage("select a from (select * from RAW.X.T) s", ["a"], schema={})
    rcl = res[0]
    assert rcl.sources == ()  # unresolved leaf -> no fabricated source
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
