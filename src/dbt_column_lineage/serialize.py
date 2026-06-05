"""Render a LineageResult to the Phase 1 output formats: internal JSON and a Mermaid diagram.
Deterministic output for clean diffs."""

import json
from pathlib import Path

from dbt_column_lineage.ir import ColumnRef, LineageResult, result_to_dict, transform_label


def to_json(result: LineageResult, *, indent: int = 2) -> str:
    """Deterministic JSON. Field order comes from the IR's ordered dict (stable across runs)."""
    return json.dumps(result_to_dict(result), indent=indent)


def write_json(result: LineageResult, path: str | Path, *, indent: int = 2) -> None:
    Path(path).write_text(to_json(result, indent=indent))


def _sanitize(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text)


def to_mermaid(result: LineageResult) -> str:
    lines = ["flowchart TD"]
    node_ids: dict[str, str] = {}

    def node_id(ref: ColumnRef) -> str:
        key = str(ref)
        if key not in node_ids:
            node_ids[key] = f"n{len(node_ids)}_{_sanitize(key)}"
        return node_ids[key]

    # distinct nodes in first-seen order (deterministic given a deterministic edge list)
    seen: set[str] = set()
    for edge in result.edges:
        for ref in (edge.upstream, edge.downstream):
            if str(ref) not in seen:
                seen.add(str(ref))
                lines.append(f'    {node_id(ref)}["{ref}"]')

    edge_lines = [
        f"    {node_id(e.upstream)} -->|{transform_label(e.transforms)}| {node_id(e.downstream)}"
        for e in result.edges
    ]
    lines.extend(sorted(edge_lines))
    return "\n".join(lines)
