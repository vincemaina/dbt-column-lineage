import json
from pathlib import Path

from dbt_column_lineage.artifacts import load_artifacts
from dbt_column_lineage.changes import changed_from_explicit, changed_from_state
from dbt_column_lineage.engine import extract_lineage
from dbt_column_lineage.hybrid import HybridSchemaResolver
from dbt_column_lineage.ir import SchemaProvenance, result_to_dict

FIXTURE = Path(__file__).parent / "fixtures" / "jaffle"
MANIFEST = FIXTURE / "manifest.json"
CATALOG = FIXTURE / "catalog.json"


def test_changed_from_explicit_resolves_names_and_uids():
    art = load_artifacts(MANIFEST, CATALOG)
    assert changed_from_explicit(art, ["stg_orders"]) == {"model.jaffle.stg_orders"}
    assert changed_from_explicit(art, ["model.jaffle.customers"]) == {"model.jaffle.customers"}
    assert changed_from_explicit(art, ["does_not_exist"]) == set()


def test_changed_from_state_compares_compiled_sql(tmp_path):
    baseline = json.loads(MANIFEST.read_text())
    baseline["nodes"]["model.jaffle.stg_orders"]["compiled_code"] += "\n-- edited"
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline))
    art = load_artifacts(MANIFEST, CATALOG)
    assert changed_from_state(art, path) == {"model.jaffle.stg_orders"}


def test_inference_set_is_changed_plus_descendants():
    resolver = HybridSchemaResolver(
        load_artifacts(MANIFEST, CATALOG), {"model.jaffle.stg_customers"}
    )
    resolver.schema()
    # stg_customers + descendants -> inferred
    assert resolver.provenance("ANALYTICS.STAGING.STG_CUSTOMERS") == SchemaProvenance.INFERRED
    assert resolver.provenance("ANALYTICS.MARTS.CUSTOMERS") == SchemaProvenance.INFERRED
    # unchanged and not a descendant -> authoritative catalog
    assert resolver.provenance("ANALYTICS.STAGING.STG_ORDERS") == SchemaProvenance.CATALOG
    assert resolver.provenance("ANALYTICS.MARTS.ORDER_WINDOW") == SchemaProvenance.CATALOG


def test_no_changes_is_all_catalog():
    resolver = HybridSchemaResolver(load_artifacts(MANIFEST, CATALOG), set())
    resolver.schema()
    assert resolver.provenance("ANALYTICS.MARTS.CUSTOMERS") == SchemaProvenance.CATALOG
    assert resolver.reconciliation() == ()


def _catalog_without(column: str, model_uid: str, tmp_path) -> Path:
    catalog = json.loads(CATALOG.read_text())
    del catalog["nodes"][model_uid]["columns"][column]
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog))
    return path


def test_reconciliation_detects_added_column(tmp_path):
    # catalog (built) lacks FIRST_NAME_CLEAN; inferred (current SQL) has it -> the change ADDS it
    patched = _catalog_without("FIRST_NAME_CLEAN", "model.jaffle.stg_customers", tmp_path)
    resolver = HybridSchemaResolver(
        load_artifacts(MANIFEST, patched), {"model.jaffle.stg_customers"}
    )
    recon = resolver.reconciliation()
    assert len(recon) == 1
    assert recon[0].asset == "model.jaffle.stg_customers"
    assert recon[0].added == ("first_name_clean",)
    assert recon[0].removed == ()


def test_reconciliation_detects_retyped_column(tmp_path):
    # catalog says first_name is NUMBER; the SQL (from a VARCHAR source) infers VARCHAR -> retyped
    catalog = json.loads(CATALOG.read_text())
    catalog["nodes"]["model.jaffle.stg_customers"]["columns"]["FIRST_NAME"]["type"] = "NUMBER"
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog))
    resolver = HybridSchemaResolver(load_artifacts(MANIFEST, path), {"model.jaffle.stg_customers"})
    diff = next(d for d in resolver.reconciliation() if d.asset == "model.jaffle.stg_customers")
    retyped = {col: (old, new) for col, old, new in diff.retyped}
    assert "first_name" in retyped  # type propagated from the upstream catalog type
    old, new = retyped["first_name"]
    assert old == "NUMBER" and "VARCHAR" in new


def test_reconciliation_ignores_normalization_noise(tmp_path):
    # catalog NUMBER vs inferred DECIMAL(38, 0) is the SAME type — must NOT be flagged as retyped
    resolver = HybridSchemaResolver(load_artifacts(MANIFEST, CATALOG), {"model.jaffle.stg_orders"})
    for diff in resolver.reconciliation():
        for col, old, new in diff.retyped:
            assert col != "customer_id", f"spurious retype {old}->{new}"


def test_hybrid_engine_end_to_end(tmp_path):
    patched = _catalog_without("FIRST_NAME_CLEAN", "model.jaffle.stg_customers", tmp_path)
    result = extract_lineage(MANIFEST, patched, schema_mode="hybrid", changed=["stg_customers"])
    assert len(result.edges) > 0  # lineage still produced
    assert any(
        d.asset == "model.jaffle.stg_customers" and "first_name_clean" in d.added
        for d in result.reconciliation
    )
    assert "reconciliation" in result_to_dict(result)  # serializes


def test_hybrid_via_state_manifest(tmp_path):
    # baseline differs on stg_customers SQL -> it's the changed model; reconciliation runs on it
    baseline = json.loads(MANIFEST.read_text())
    baseline["nodes"]["model.jaffle.stg_customers"]["compiled_code"] += "\n-- edited"
    base_path = tmp_path / "baseline.json"
    base_path.write_text(json.dumps(baseline))
    result = extract_lineage(MANIFEST, CATALOG, schema_mode="hybrid", state_manifest=base_path)
    # stg_customers SQL matches its catalog, so no column diff, but the run succeeds with edges
    assert len(result.edges) == 26
