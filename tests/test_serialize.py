import json

from dbt_column_lineage.ir import (
    ColumnRef,
    LineageEdge,
    LineageResult,
    LineageType,
    TransformKind,
    TransformStep,
    result_to_dict,
)
from dbt_column_lineage.serialize import to_json, to_mermaid, write_json

RESULT = LineageResult(
    edges=(
        LineageEdge(
            downstream=ColumnRef("model.b", "y"),
            upstream=ColumnRef("model.a", "x"),
            lineage_type=LineageType.DIRECT,
            transforms=(
                TransformStep(TransformKind.JOIN, {"join_type": "LEFT", "introduces_nulls": True}),
                TransformStep(TransformKind.RENAME, {"from": "x", "to": "y"}),
            ),
        ),
    ),
    processed_assets=("model.b",),
)


def test_to_json_roundtrips_to_result_dict():
    assert json.loads(to_json(RESULT)) == result_to_dict(RESULT)


def test_to_json_is_stable():
    assert to_json(RESULT) == to_json(RESULT)


def test_write_json(tmp_path):
    path = tmp_path / "out.json"
    write_json(RESULT, path)
    assert json.loads(path.read_text()) == result_to_dict(RESULT)


def test_mermaid_structure():
    text = to_mermaid(RESULT)
    assert text.startswith("flowchart TD")
    assert '"model.a.x"' in text and '"model.b.y"' in text
    assert "JOIN→RENAME" in text  # edge label = the chain summary
    assert "-->|" in text


def test_mermaid_is_deterministic():
    assert to_mermaid(RESULT) == to_mermaid(RESULT)
