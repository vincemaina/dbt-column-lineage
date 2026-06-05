"""Change detection for hybrid mode: which models did a PR modify? Two pluggable sources — an explicit
set of model names/unique_ids, and dbt `state:modified` (compare compiled SQL against a baseline
manifest). Pure (no sqlglot)."""

from pathlib import Path

from dbt_column_lineage.artifacts import DbtArtifacts, load_manifest


def changed_from_explicit(artifacts: DbtArtifacts, names_or_uids: list[str]) -> set[str]:
    """Resolve explicit model names or unique_ids to model unique_ids."""
    by_name = {n.name: uid for uid, n in artifacts.nodes.items() if n.resource_type == "model"}
    result: set[str] = set()
    for token in names_or_uids:
        token = token.strip()
        if token in artifacts.nodes:
            result.add(token)
        elif token in by_name:
            result.add(by_name[token])
    return result


def changed_from_state(artifacts: DbtArtifacts, baseline_manifest_path: str | Path) -> set[str]:
    """state:modified — models whose compiled SQL differs from a baseline manifest (or are new)."""
    baseline_nodes, _, _, _ = load_manifest(baseline_manifest_path)
    result: set[str] = set()
    for uid, node in artifacts.nodes.items():
        if node.resource_type != "model" or not node.compiled_code:
            continue
        baseline = baseline_nodes.get(uid)
        if baseline is None or baseline.compiled_code != node.compiled_code:
            result.add(uid)
    return result
