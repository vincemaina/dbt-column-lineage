import pytest

from dbt_column_lineage.graph import LineageGraph, parse_column_ref
from dbt_column_lineage.ir import (
    ColumnRef,
    LineageEdge,
    LineageType,
    TransformKind,
    TransformStep,
)


def _edge(up_asset, up_col, down_asset, down_col):
    return LineageEdge(
        downstream=ColumnRef(down_asset, down_col),
        upstream=ColumnRef(up_asset, up_col),
        lineage_type=LineageType.DIRECT,
        transforms=(TransformStep(TransformKind.IDENTITY),),
    )


# a -> b -> c chain
CHAIN = [
    _edge("model.a", "x", "model.b", "x"),
    _edge("model.b", "x", "model.c", "x"),
]


def test_parse_column_ref_splits_on_last_dot():
    ref = parse_column_ref("model.jaffle.customers.lifetime_value")
    assert ref == ColumnRef("model.jaffle.customers", "lifetime_value")


def test_parse_column_ref_lowercases():
    assert parse_column_ref("model.a.X").column == "x"


def test_parse_column_ref_requires_dot():
    with pytest.raises(ValueError):
        parse_column_ref("nodot")


def test_transitive_upstream():
    g = LineageGraph(CHAIN)
    ups = g.upstream(ColumnRef("model.c", "x"))
    assert [str(r) for r in ups] == ["model.a.x", "model.b.x"]


def test_direct_only_upstream():
    g = LineageGraph(CHAIN)
    ups = g.upstream(ColumnRef("model.c", "x"), transitive=False)
    assert [str(r) for r in ups] == ["model.b.x"]


def test_transitive_downstream():
    g = LineageGraph(CHAIN)
    downs = g.downstream(ColumnRef("model.a", "x"))
    assert [str(r) for r in downs] == ["model.b.x", "model.c.x"]


def test_no_edges_returns_empty():
    g = LineageGraph(CHAIN)
    assert g.upstream(ColumnRef("model.unknown", "x")) == []


def test_cycle_terminates():
    # a <-> b cycle: upstream(a) reaches b, then b's upstream (a) is the start and is excluded.
    cyclic = [_edge("model.a", "x", "model.b", "x"), _edge("model.b", "x", "model.a", "x")]
    g = LineageGraph(cyclic)
    ups = g.upstream(ColumnRef("model.a", "x"))
    assert [str(r) for r in ups] == ["model.b.x"]  # terminates, start excluded, each node once


def test_results_deterministic():
    g = LineageGraph(CHAIN)
    assert g.upstream(ColumnRef("model.c", "x")) == g.upstream(ColumnRef("model.c", "x"))
