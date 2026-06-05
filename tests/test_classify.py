import json
from pathlib import Path


from dbt_column_lineage.artifacts import load_artifacts
from dbt_column_lineage.classify import build_model_edges, build_transform_chain
from dbt_column_lineage.ir import TransformKind, edge_to_dict
from dbt_column_lineage.schema_resolver import CatalogSchemaResolver
from dbt_column_lineage.sql_adapter import extract_column_lineage

FIXTURE = Path(__file__).parent / "fixtures" / "jaffle"


def _all_edges():
    artifacts = load_artifacts(FIXTURE / "manifest.json", FIXTURE / "catalog.json")
    resolver = CatalogSchemaResolver(artifacts)
    schema = resolver.schema()
    r2u = artifacts.relation_to_uid()
    edges = []
    all_warnings = []
    for node in artifacts.models():
        cols = [c.name.lower() for c in artifacts.catalog[node.unique_id].columns]
        raw = extract_column_lineage(node.compiled_code, cols, schema)
        e, w, _ = build_model_edges(node, raw, r2u, resolver)
        edges.extend(e)
        all_warnings.extend(w)
    return edges, all_warnings


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


def test_pipeline_matches_oracle():
    """The full 04->05->06->07 pipeline reproduces the hand-verified chain oracle exactly."""
    edges, warnings = _all_edges()
    produced = {_key(edge_to_dict(e)) for e in edges if e.lineage_type.value == "DIRECT"}
    expected_edges = json.loads((FIXTURE / "expected_lineage.json").read_text())["edges"]
    expected = {_key(e) for e in expected_edges}
    assert produced == expected
    assert warnings == []  # fully cataloged fixture -> no warnings


def test_confidence_high_for_catalog_edges():
    edges, _ = _all_edges()
    assert all(e.confidence.value == "high" for e in edges)


def _chain(model, col):
    """Convenience: build the transform chain for one fixture column (single-source)."""
    artifacts = load_artifacts(FIXTURE / "manifest.json", FIXTURE / "catalog.json")
    schema = CatalogSchemaResolver(artifacts).schema()
    node = artifacts.get_node(model)
    raw = extract_column_lineage(node.compiled_code, [col], schema)[0]
    return [build_transform_chain(s, col) for s in raw.sources]


def test_join_then_rename_chain():
    (chain,) = _chain("model.jaffle.order_enriched", "customer_first_name")
    kinds = [s.kind for s in chain]
    assert kinds == [TransformKind.JOIN, TransformKind.RENAME]
    assert chain[0].detail == {"join_type": "LEFT", "introduces_nulls": True}
    assert chain[1].detail == {"from": "first_name", "to": "customer_first_name"}


def test_unmapped_relation_warns_no_edge():
    # a source whose relation isn't in relation_to_uid -> warning, no edge
    artifacts = load_artifacts(FIXTURE / "manifest.json", FIXTURE / "catalog.json")
    resolver = CatalogSchemaResolver(artifacts)
    node = artifacts.get_node("model.jaffle.stg_orders")
    raw = extract_column_lineage(node.compiled_code, ["order_id"], resolver.schema())
    edges, warnings, _ = build_model_edges(node, raw, {}, resolver)  # empty relation map
    assert edges == []
    assert any(w.startswith("unmapped_relation:") for w in warnings)


def test_expression_kind_for_arithmetic():
    # not in the fixture: a scalar arithmetic expression -> EXPRESSION step
    schema = {"DB.S.T": {"A": "NUMBER", "B": "NUMBER"}}
    raw = extract_column_lineage("select a + b as c from DB.S.T", ["c"], schema)[0]
    chains = [build_transform_chain(s, "c") for s in raw.sources]
    assert all(c[0].kind == TransformKind.EXPRESSION for c in chains)
    assert chains[0][0].detail == {"op": "add"}  # arithmetic operator recorded (#4)


def _first_chain(sql: str, col: str, schema: dict):
    raw = extract_column_lineage(sql, [col], schema)[0]
    return build_transform_chain(raw.sources[0], col)


_T = {"DB.S.T": {"X": "NUMBER", "Y": "NUMBER", "TS": "NUMBER"}}


def test_try_cast_flagged_safe_plain_cast_not():
    safe = _first_chain("select try_cast(x as int) as r from DB.S.T", "r", _T)
    plain = _first_chain("select cast(x as int) as r from DB.S.T", "r", _T)
    assert safe[0].kind == TransformKind.CAST and safe[0].detail.get("safe") is True
    assert plain[0].kind == TransformKind.CAST and "safe" not in plain[0].detail


def test_case_else_null_flag():
    no_else = _first_chain("select case when y > 0 then x end as r from DB.S.T", "r", _T)
    with_else = _first_chain("select case when y > 0 then x else y end as r from DB.S.T", "r", _T)
    case_steps = [s for s in no_else if s.kind == TransformKind.CASE]
    assert case_steps and case_steps[0].detail["else_null"] is True
    case_steps2 = [s for s in with_else if s.kind == TransformKind.CASE]
    assert case_steps2 and case_steps2[0].detail["else_null"] is False


def test_count_distinct_flagged():
    distinct = _first_chain("select count(distinct x) as r from DB.S.T", "r", _T)
    plain = _first_chain("select count(x) as r from DB.S.T", "r", _T)
    agg = [s for s in distinct if s.kind == TransformKind.AGGREGATION][0]
    assert agg.detail.get("distinct") is True
    assert "distinct" not in [s for s in plain if s.kind == TransformKind.AGGREGATION][0].detail


def test_nullif_marked_null_introducing():
    chain = _first_chain("select nullif(x, y) as r from DB.S.T", "r", _T)
    nullif = [s for s in chain if s.detail.get("func") == "NULLIF"]
    assert nullif and nullif[0].detail["introduces_nulls"] is True


def test_window_frame_recorded():
    chain = _first_chain(
        "select sum(x) over (order by ts rows between 1 preceding and current row) as r from DB.S.T",
        "r",
        _T,
    )
    win = [s for s in chain if s.kind == TransformKind.WINDOW][0]
    assert "ROWS" in win.detail["frame"].upper()
