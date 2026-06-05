"""Resolve a dbt-style selection string to model unique_ids. Phase 1 subset: names, graph operators
(+ancestors / descendants+), path:, plus space=union and comma=intersection. tag:/package:/numeric
depth are out of scope.
"""

from dbt_column_lineage.artifacts import DbtArtifacts


def _resolve_name(artifacts: DbtArtifacts, name: str) -> str | None:
    for uid, node in artifacts.nodes.items():
        if node.resource_type == "model" and node.name == name:
            return uid
    return None


def _transitive(graph: dict[str, tuple[str, ...]], start: str) -> set[str]:
    out: set[str] = set()
    stack = list(graph.get(start, ()))
    while stack:
        cur = stack.pop()
        if cur not in out:
            out.add(cur)
            stack.extend(graph.get(cur, ()))
    return out


def _match_token(artifacts: DbtArtifacts, token: str, model_ids: set[str]) -> set[str]:
    token = token.strip()
    if not token:
        return set()
    if token.startswith("path:"):
        prefix = token[len("path:") :]
        return {
            uid
            for uid in model_ids
            if (artifacts.get_node(uid).original_file_path or "").startswith(prefix)
        }
    want_ancestors = token.startswith("+")
    want_descendants = token.endswith("+")
    name = token.strip("+")
    base = _resolve_name(artifacts, name)
    if base is None:
        return set()
    selected = {base}
    if want_ancestors:
        selected |= _transitive(artifacts.parent_map, base)
    if want_descendants:
        selected |= _transitive(artifacts.child_map, base)
    return selected & model_ids  # ancestors may include sources/seeds; only models are targets


def select_nodes(artifacts: DbtArtifacts, selector: str | None) -> list[str]:
    model_ids = {n.unique_id for n in artifacts.models()}
    if not selector or not selector.strip():
        return sorted(model_ids)
    result: set[str] = set()
    for union_part in selector.split():  # space = union
        intersection: set[str] | None = None
        for token in union_part.split(","):  # comma = intersection
            matched = _match_token(artifacts, token, model_ids)
            intersection = matched if intersection is None else (intersection & matched)
        if intersection:
            result |= intersection
    return sorted(result)
