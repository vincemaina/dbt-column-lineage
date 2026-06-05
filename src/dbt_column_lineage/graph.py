"""Queryable lineage graph over LineageEdges: transitive upstream/downstream for a column, cycle-safe.
Pure IR in, pure IR out — no SQLGlot, no artifacts.
"""

from collections import deque
from collections.abc import Callable, Iterable

from dbt_column_lineage.ir import ColumnRef, LineageEdge


def parse_column_ref(text: str) -> ColumnRef:
    """'model.jaffle.customers.lifetime_value' -> ColumnRef('model.jaffle.customers', 'lifetime_value').
    Splits on the LAST dot (asset ids contain dots); column is lower-cased."""
    asset, sep, column = text.rpartition(".")
    if not sep:
        raise ValueError(f"Expected 'asset.column', got {text!r}")
    return ColumnRef(asset, column.lower())


class LineageGraph:
    def __init__(self, edges: Iterable[LineageEdge]) -> None:
        self._into: dict[ColumnRef, list[LineageEdge]] = {}
        self._out: dict[ColumnRef, list[LineageEdge]] = {}
        for edge in edges:
            self._into.setdefault(edge.downstream, []).append(edge)
            self._out.setdefault(edge.upstream, []).append(edge)

    def edges_into(self, ref: ColumnRef) -> list[LineageEdge]:
        return list(self._into.get(ref, []))

    def edges_out_of(self, ref: ColumnRef) -> list[LineageEdge]:
        return list(self._out.get(ref, []))

    def upstream(self, ref: ColumnRef, *, transitive: bool = True) -> list[ColumnRef]:
        return self._reach(ref, self._into, lambda e: e.upstream, transitive)

    def downstream(self, ref: ColumnRef, *, transitive: bool = True) -> list[ColumnRef]:
        return self._reach(ref, self._out, lambda e: e.downstream, transitive)

    @staticmethod
    def _reach(
        start: ColumnRef,
        adjacency: dict[ColumnRef, list[LineageEdge]],
        pick: Callable[[LineageEdge], ColumnRef],
        transitive: bool,
    ) -> list[ColumnRef]:
        visited = {start}
        found: list[ColumnRef] = []
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for edge in adjacency.get(current, ()):
                nxt = pick(edge)
                if nxt not in visited:
                    visited.add(nxt)
                    found.append(nxt)
                    if transitive:
                        queue.append(nxt)
            if not transitive:
                break  # expand only the start node
        return sorted(found, key=str)
