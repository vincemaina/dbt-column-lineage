from pathlib import Path

import pytest

from dbt_column_lineage.artifacts import load_artifacts
from dbt_column_lineage.selection import select_nodes

FIXTURE = Path(__file__).parent / "fixtures" / "jaffle"


@pytest.fixture
def artifacts():
    return load_artifacts(FIXTURE / "manifest.json", FIXTURE / "catalog.json")


def test_none_selects_all_models(artifacts):
    assert len(select_nodes(artifacts, None)) == 7


def test_bare_name(artifacts):
    assert select_nodes(artifacts, "customers") == ["model.jaffle.customers"]


def test_ancestors(artifacts):
    got = set(select_nodes(artifacts, "+customers"))
    assert got == {
        "model.jaffle.customers",
        "model.jaffle.stg_customers",
        "model.jaffle.stg_orders",
    }


def test_descendants(artifacts):
    got = set(select_nodes(artifacts, "stg_orders+"))
    assert got == {
        "model.jaffle.stg_orders",
        "model.jaffle.customers",
        "model.jaffle.order_enriched",
        "model.jaffle.order_window",
    }


def test_path_selector(artifacts):
    got = set(select_nodes(artifacts, "path:models/staging"))
    assert got == {"model.jaffle.stg_orders", "model.jaffle.stg_customers"}


def test_union_with_space(artifacts):
    got = set(select_nodes(artifacts, "customers all_names"))
    assert got == {"model.jaffle.customers", "model.jaffle.all_names"}


def test_intersection_with_comma(artifacts):
    # descendants of stg_orders INTERSECT descendants of stg_customers
    got = set(select_nodes(artifacts, "stg_orders+,stg_customers+"))
    assert got == {"model.jaffle.customers", "model.jaffle.order_enriched"}


def test_unknown_name_returns_empty(artifacts):
    assert select_nodes(artifacts, "does_not_exist") == []
