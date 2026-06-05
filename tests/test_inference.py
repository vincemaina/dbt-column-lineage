import json
from pathlib import Path

from dbt_column_lineage.artifacts import load_artifacts
from dbt_column_lineage.engine import extract_lineage
from dbt_column_lineage.inference import InferredSchemaResolver
from dbt_column_lineage.ir import SchemaProvenance, edge_to_dict

FIXTURE = Path(__file__).parent / "fixtures" / "jaffle"
MANIFEST = FIXTURE / "manifest.json"
CATALOG = FIXTURE / "catalog.json"


def test_infers_model_schemas_without_catalog():
    resolver = InferredSchemaResolver(load_artifacts(MANIFEST))  # no catalog
    schema = resolver.schema()
    assert set(schema["ANALYTICS.STAGING.STG_ORDERS"]) == {
        "ORDER_ID",
        "CUSTOMER_ID",
        "AMOUNT",
        "STATUS",
        "ORDERED_AT",
    }
    assert set(schema["ANALYTICS.MARTS.CUSTOMERS"]) == {
        "CUSTOMER_ID",
        "FIRST_NAME",
        "NUMBER_OF_ORDERS",
        "LIFETIME_VALUE",
    }


def test_star_inferred_via_dag_order():
    # star_passthrough does `select *` from stg_customers; topo order must infer stg_customers first
    resolver = InferredSchemaResolver(load_artifacts(MANIFEST))
    assert set(resolver.schema()["ANALYTICS.MARTS.STAR_PASSTHROUGH"]) == {
        "CUSTOMER_ID",
        "FIRST_NAME",
        "LAST_NAME",
        "FIRST_NAME_CLEAN",
    }


def test_provenance_models_and_derived_sources_inferred():
    # without a catalog seed, a referenced source's columns are derived from usage -> inferred;
    # a relation that is never referenced stays unknown.
    resolver = InferredSchemaResolver(load_artifacts(MANIFEST))
    resolver.schema()
    assert resolver.provenance("ANALYTICS.STAGING.STG_ORDERS") == SchemaProvenance.INFERRED
    assert resolver.provenance("RAW.JAFFLE.RAW_ORDERS") == SchemaProvenance.INFERRED
    assert resolver.provenance("NOPE.NOPE.NOPE") == SchemaProvenance.UNKNOWN


def test_seed_sources_get_catalog_provenance():
    resolver = InferredSchemaResolver(
        load_artifacts(MANIFEST), seed={"RAW.JAFFLE.RAW_ORDERS": {"ID": "NUMBER"}}
    )
    resolver.schema()
    assert resolver.provenance("RAW.JAFFLE.RAW_ORDERS") == SchemaProvenance.CATALOG


def _steps(transforms):
    return tuple((s["kind"], tuple(sorted(s["detail"].items()))) for s in transforms)


def _key(edge_like):
    return (
        edge_like["downstream"]["asset"],
        edge_like["downstream"]["column"],
        edge_like["upstream"]["asset"],
        edge_like["upstream"]["column"],
        _steps(edge_like["transforms"]),
    )


def test_inferred_mode_reproduces_oracle_edges():
    """Inferred mode (NO catalog) reproduces the same edges as catalog mode — only provenance differs."""
    result = extract_lineage(MANIFEST, None, schema_mode="inferred")
    produced = {_key(edge_to_dict(e)) for e in result.edges if e.lineage_type.value == "DIRECT"}
    expected = {
        _key(e) for e in json.loads((FIXTURE / "expected_lineage.json").read_text())["edges"]
    }
    assert produced == expected
    assert all(e.schema_provenance != SchemaProvenance.CATALOG for e in result.edges)


def test_auto_mode_prefers_catalog_when_present():
    result = extract_lineage(MANIFEST, CATALOG, schema_mode="auto")
    assert all(e.schema_provenance == SchemaProvenance.CATALOG for e in result.edges)


def test_auto_mode_falls_back_to_inferred_without_catalog():
    result = extract_lineage(MANIFEST, None, schema_mode="auto")
    assert len(result.edges) == 26  # same graph, inferred
    assert all(e.schema_provenance != SchemaProvenance.CATALOG for e in result.edges)
