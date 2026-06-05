"""Ephemeral re-attribution: dbt inlines ephemeral models as `__dbt__cte__<name>` CTEs; we restore
them as graph nodes by stubbing those CTE bodies to read from the ephemeral's relation."""

import json
from pathlib import Path

from dbt_column_lineage.engine import extract_lineage
from dbt_column_lineage.ephemeral import rewrite_ephemeral_ctes
from dbt_column_lineage.graph import LineageGraph
from dbt_column_lineage.ir import ColumnRef, LineageType


def test_rewrite_stubs_inlined_cte_to_relation():
    sql = (
        "WITH __dbt__cte__eph AS (SELECT a + 1 AS x FROM RAW.S.SRC), "
        "calcs AS (SELECT x FROM __dbt__cte__eph) "
        "SELECT x FROM calcs"
    )
    out = rewrite_ephemeral_ctes(sql, {"__dbt__cte__eph": "DB.S.EPH"}, "snowflake")
    assert "DB.S.EPH" in out
    assert "A + 1" not in out.upper()  # the ephemeral's own logic is no longer inlined in the consumer


def test_rewrite_noop_without_ephemeral_ctes():
    sql = "SELECT a FROM RAW.S.T"
    assert rewrite_ephemeral_ctes(sql, {"__dbt__cte__eph": "DB.S.EPH"}, "snowflake") == sql


def _write_manifest(tmp: Path) -> Path:
    """A source -> ephemeral -> consumer chain. The consumer's compiled SQL inlines the ephemeral as a
    `__dbt__cte__eph` CTE, exactly as dbt compiles it."""
    def node(**kw):
        return {"resource_type": "model", "original_file_path": "m.sql", **kw}

    manifest = {
        "nodes": {
            "model.p.eph": node(
                unique_id="model.p.eph",
                name="eph",
                database="DB",
                schema="S",
                alias="EPH",
                config={"materialized": "ephemeral"},
                depends_on={"nodes": ["source.p.raw.src"]},
                compiled_code="select id, amount + 1 as amt from RAW.S.SRC",
            ),
            "model.p.consumer": node(
                unique_id="model.p.consumer",
                name="consumer",
                database="DB",
                schema="S",
                alias="CONSUMER",
                config={"materialized": "table"},
                depends_on={"nodes": ["model.p.eph"]},
                compiled_code=(
                    "with __dbt__cte__eph as (select id, amount + 1 as amt from RAW.S.SRC) "
                    "select id, amt from __dbt__cte__eph"
                ),
            ),
        },
        "sources": {
            "source.p.raw.src": {
                "resource_type": "source",
                "name": "src",
                "database": "RAW",
                "schema": "S",
                "identifier": "SRC",
            }
        },
        "parent_map": {},
        "child_map": {},
    }
    path = tmp / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def test_ephemeral_is_reattributed_as_node(tmp_path):
    result = extract_lineage(_write_manifest(tmp_path), None, schema_mode="inferred")
    direct = [e for e in result.edges if e.lineage_type == LineageType.DIRECT]
    into = {(e.downstream.column, e.upstream.column) for e in direct if e.upstream.asset == "model.p.eph"}
    outof = {(e.downstream.column, e.upstream.column) for e in direct if e.downstream.asset == "model.p.eph"}
    # consumer reads `amt` and `id` FROM the ephemeral (not jumping straight to RAW.S.SRC)
    assert ("amt", "amt") in into and ("id", "id") in into
    # the ephemeral itself is analyzed: amt <- src.amount (through the + 1 expression)
    assert ("amt", "amount") in outof and ("id", "id") in outof
    assert "model.p.eph" in result.processed_assets


def test_graph_traverses_through_ephemeral(tmp_path):
    result = extract_lineage(_write_manifest(tmp_path), None, schema_mode="inferred")
    graph = LineageGraph(result.edges)
    # upstream of the consumer's `amt` reaches the source THROUGH the ephemeral node
    upstream = {str(c) for c in graph.upstream(ColumnRef("model.p.consumer", "amt"))}
    assert "model.p.eph.amt" in upstream
    assert "source.p.raw.src.amount" in upstream
