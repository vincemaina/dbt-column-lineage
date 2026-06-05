import inspect
from pathlib import Path

import pytest

from dbt_column_lineage import schema_resolver as sr_module
from dbt_column_lineage.artifacts import load_artifacts
from dbt_column_lineage.ir import SchemaProvenance
from dbt_column_lineage.schema_resolver import CatalogSchemaResolver

FIXTURE = Path(__file__).parent / "fixtures" / "jaffle"


@pytest.fixture
def resolver():
    artifacts = load_artifacts(FIXTURE / "manifest.json", FIXTURE / "catalog.json")
    return CatalogSchemaResolver(artifacts)


def test_schema_has_model_columns(resolver):
    schema = resolver.schema()
    assert schema["ANALYTICS.STAGING.STG_ORDERS"] == {
        "ORDER_ID": "NUMBER",
        "CUSTOMER_ID": "NUMBER",
        "AMOUNT": "NUMBER",
        "STATUS": "VARCHAR",
        "ORDERED_AT": "TIMESTAMP_NTZ",
    }


def test_schema_has_source_columns(resolver):
    assert set(resolver.schema()["RAW.JAFFLE.RAW_ORDERS"]) == {
        "ID",
        "CUSTOMER_ID",
        "AMOUNT",
        "STATUS",
        "ORDERED_AT",
    }


def test_star_passthrough_resolves_to_four_columns(resolver):
    assert set(resolver.schema()["ANALYTICS.MARTS.STAR_PASSTHROUGH"]) == {
        "CUSTOMER_ID",
        "FIRST_NAME",
        "LAST_NAME",
        "FIRST_NAME_CLEAN",
    }


def test_provenance(resolver):
    assert resolver.provenance("ANALYTICS.STAGING.STG_ORDERS") == SchemaProvenance.CATALOG
    assert resolver.provenance("X.Y.Z") == SchemaProvenance.UNKNOWN


def test_no_sqlglot_import():
    assert "sqlglot" not in inspect.getsource(sr_module)
