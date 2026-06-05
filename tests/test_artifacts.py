from pathlib import Path

import pytest

from dbt_column_lineage.artifacts import Relation, load_artifacts, load_manifest

FIXTURE = Path(__file__).parent / "fixtures" / "jaffle"
MANIFEST = FIXTURE / "manifest.json"
CATALOG = FIXTURE / "catalog.json"


@pytest.fixture
def artifacts():
    return load_artifacts(MANIFEST, CATALOG)


def test_relation_key_uppercases():
    assert Relation("analytics", "staging", "stg_orders").key() == "ANALYTICS.STAGING.STG_ORDERS"


def test_loads_all_models(artifacts):
    model_ids = {n.unique_id for n in artifacts.models()}
    assert len(model_ids) == 7
    assert "model.jaffle.customers" in model_ids


def test_loads_sources(artifacts):
    assert set(artifacts.sources) == {
        "source.jaffle.raw.raw_orders",
        "source.jaffle.raw.raw_customers",
    }


def test_catalog_covers_models_and_sources(artifacts):
    assert "model.jaffle.stg_orders" in artifacts.catalog
    assert "source.jaffle.raw.raw_orders" in artifacts.catalog


def test_relation_to_uid_maps_models_and_sources(artifacts):
    r2u = artifacts.relation_to_uid()
    assert r2u["ANALYTICS.STAGING.STG_ORDERS"] == "model.jaffle.stg_orders"
    assert r2u["RAW.JAFFLE.RAW_ORDERS"] == "source.jaffle.raw.raw_orders"


def test_model_has_compiled_code_source_does_not(artifacts):
    customers = artifacts.get_node("model.jaffle.customers")
    assert customers is not None
    assert "count(o.order_id) as number_of_orders" in customers.compiled_code
    src = artifacts.get_node("source.jaffle.raw.raw_orders")
    assert src is not None and src.compiled_code is None


def test_source_relation_uses_identifier(artifacts):
    src = artifacts.get_node("source.jaffle.raw.raw_orders")
    assert src.relation.name == "RAW_ORDERS"  # identifier, not the source `name`


def test_parent_and_child_maps_roundtrip(artifacts):
    assert artifacts.parent_map["model.jaffle.customers"] == (
        "model.jaffle.stg_customers",
        "model.jaffle.stg_orders",
    )
    assert "model.jaffle.customers" in artifacts.child_map["model.jaffle.stg_orders"]


def test_load_manifest_returns_four_parts():
    nodes, sources, parent_map, child_map = load_manifest(MANIFEST)
    assert len(nodes) == 7 and len(sources) == 2
    assert isinstance(parent_map["model.jaffle.stg_orders"], tuple)


def test_bad_path_raises_valueerror():
    with pytest.raises(ValueError):
        load_artifacts("/no/such/manifest.json", CATALOG)
