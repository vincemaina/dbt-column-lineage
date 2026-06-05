import json
from pathlib import Path

from dbt_column_lineage.engine import extract_lineage
from dbt_column_lineage.graph import LineageGraph, parse_column_ref
from dbt_column_lineage.ir import edge_to_dict

FIXTURE = Path(__file__).parent / "fixtures" / "jaffle"
MANIFEST = FIXTURE / "manifest.json"
CATALOG = FIXTURE / "catalog.json"


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


def test_extract_matches_oracle_end_to_end():
    result = extract_lineage(MANIFEST, CATALOG)
    produced = {_key(edge_to_dict(e)) for e in result.edges}
    expected = {
        _key(e)
        for e in json.loads(CATALOG.parent.joinpath("expected_lineage.json").read_text())["edges"]
    }
    assert produced == expected
    assert result.warnings == ()
    assert len(result.processed_assets) == 7


def test_upstream_transitive():
    result = extract_lineage(MANIFEST, CATALOG)
    g = LineageGraph(result.edges)
    ups = {str(r) for r in g.upstream(parse_column_ref("model.jaffle.customers.lifetime_value"))}
    assert "model.jaffle.stg_orders.amount" in ups
    assert "source.jaffle.raw.raw_orders.amount" in ups


def test_downstream_transitive():
    result = extract_lineage(MANIFEST, CATALOG)
    g = LineageGraph(result.edges)
    downs = {str(r) for r in g.downstream(parse_column_ref("source.jaffle.raw.raw_orders.amount"))}
    assert "model.jaffle.stg_orders.amount" in downs
    assert "model.jaffle.customers.lifetime_value" in downs


def test_select_scopes_extraction():
    result = extract_lineage(MANIFEST, CATALOG, select="stg_orders")
    assert {e.downstream.asset for e in result.edges} == {"model.jaffle.stg_orders"}


def test_missing_catalog_entry_warns_and_continues(tmp_path):
    catalog = json.loads(CATALOG.read_text())
    del catalog["nodes"]["model.jaffle.customers"]
    patched = tmp_path / "catalog.json"
    patched.write_text(json.dumps(catalog))
    result = extract_lineage(MANIFEST, patched)
    assert any(w.startswith("no_schema:model.jaffle.customers") for w in result.warnings)
    assert "model.jaffle.stg_orders" in result.processed_assets  # others still processed
