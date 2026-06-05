"""Thin adapter over SQLGlot's lineage(): for one compiled model, find each output column's upstream
base-table column AND the full ordered path of projection expressions it flows through (across every
CTE/subquery hop). One of only two modules that import sqlglot (the other is classify.py).

Key design (informed by how sqlglot's lineage Node tree works): the transform at each hop lives in that
node's OWN `.expression`. We enumerate every root->leaf path (our own recursion, not Node.walk which
dedups by id and loses paths; cycle-guarded; depth/branch capped) and hand the classifier the ordered
hop expressions so it can build a chain that spans CTEs. Top-level set operations are decomposed into
branch SELECTs for clean branch indices. Errors are contained: a parse/lineage failure for a column
yields a warned, empty-source result.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

import sqlglot
from sqlglot import MappingSchema, exp
from sqlglot.errors import SqlglotError
from sqlglot.lineage import Node, lineage

from dbt_column_lineage.schema_resolver import SchemaMapping

_SET_OPS = tuple(
    c
    for c in (getattr(exp, n, None) for n in ("Union", "Except", "Intersect"))
    if isinstance(c, type)
)
_MAX_DEPTH = 100  # guard pathological CTE nesting
_MAX_PATHS = 4000  # guard diamond-CTE path explosion per column


@dataclass(frozen=True)
class RawHop:
    expression: exp.Expression  # the projection (Alias) at this hop
    join: (
        tuple[str, bool] | None
    )  # (join_type, introduces_nulls) for the column consumed here, else None


@dataclass(frozen=True)
class RawSource:
    relation_key: str | None  # base table "DB.SCHEMA.TABLE" (UPPER)
    column: str  # leaf (base-table) column, as sqlglot reports it (UPPER for Snowflake)
    hops: tuple[RawHop, ...]  # per hop, ordered SOURCE(deepest) -> OUTPUT(root)
    branch_index: int | None  # set-operation branch index, else None


@dataclass(frozen=True)
class RawColumnLineage:
    output_column: str
    is_set_operation: bool
    sources: tuple[RawSource, ...]
    warnings: tuple[str, ...]


def _to_sqlglot_schema(schema: SchemaMapping) -> dict:
    nested: dict = {}
    for key, cols in schema.items():
        parts = key.split(".")
        if len(parts) != 3 or not cols:  # sqlglot rejects a table with no columns
            continue
        db, sch, tbl = parts
        nested.setdefault(db, {}).setdefault(sch, {})[tbl] = dict(cols)
    return nested


def build_sqlglot_schema(schema: SchemaMapping, dialect: str = "snowflake") -> MappingSchema:
    """Build the reusable SQLGlot schema ONCE. For large catalogs this normalization costs tens of ms,
    and SQLGlot rebuilds it on every lineage() call — so the engine builds it once and passes it to
    extract_column_lineage for every model."""
    return MappingSchema(_to_sqlglot_schema(schema), dialect=dialect)


def _flatten_setops(expr: exp.Expression) -> list[exp.Expression]:
    if isinstance(expr, _SET_OPS):
        return _flatten_setops(expr.this) + _flatten_setops(expr.expression)
    return [expr]


def _join_context(select: exp.Expression) -> tuple[str | None, dict[str, tuple[str, bool]]]:
    """(anchor_alias, {join_alias: (join_type, introduces_nulls)}), keyed by the alias columns use.
    The FROM anchor is preserved; LEFT/RIGHT/FULL-joined relations are the nullable side."""
    anchor: str | None = None
    joined: dict[str, tuple[str, bool]] = {}
    if not isinstance(select, exp.Select):
        return anchor, joined
    from_ = select.args.get("from")
    if from_ is not None:
        anchor = (from_.this.alias_or_name or "").lower()
    for join in select.args.get("joins") or []:
        alias = (join.this.alias_or_name or "").lower()
        side = (join.args.get("side") or "").upper()
        kind = (join.args.get("kind") or "").upper()
        joined[alias] = (side or kind or "INNER", side in ("LEFT", "RIGHT", "FULL"))
    return anchor, joined


def _paths(node: Node) -> Iterator[tuple[Node, ...]]:
    """Every root->leaf path. Own recursion (Node.walk dedups by id and loses paths); cycle-guarded by a
    path-local id set; depth-capped."""

    def rec(n: Node, prefix: tuple[Node, ...], seen: frozenset[int]) -> Iterator[tuple[Node, ...]]:
        if id(n) in seen or len(prefix) >= _MAX_DEPTH:
            yield (*prefix, n)
            return
        prefix = (*prefix, n)
        if not n.downstream:
            yield prefix
            return
        seen = seen | {id(n)}
        for child in n.downstream:
            yield from rec(child, prefix, seen)

    yield from rec(node, (), frozenset())


def _path_to_source(
    path: tuple[Node, ...], branch_index: int | None
) -> tuple[RawSource | None, str | None]:
    leaf = path[-1]
    if not isinstance(leaf.expression, exp.Table):
        return None, ("select_star_unresolved" if leaf.name == "*" else "unresolved_column")
    leaf_column = leaf.name.split(".")[-1]
    if leaf_column == "*":
        return None, "select_star_unresolved"
    relation_key = exp.table_name(leaf.expression).upper()
    non_leaf = path[:-1]  # root .. deepest
    hops: list[RawHop] = []
    for i, node in enumerate(non_leaf):
        consumed = path[i + 1]  # the node toward the leaf that this hop consumes
        _, joined = _join_context(node.source)  # join context of THIS hop's scope
        alias = consumed.name.rsplit(".", 1)[0].lower() if "." in consumed.name else None
        hops.append(RawHop(node.expression, joined.get(alias)))
    hops.reverse()  # SOURCE(deepest) -> OUTPUT(root)
    return RawSource(relation_key, leaf_column, tuple(hops), branch_index), None


def extract_column_lineage(
    compiled_sql: str,
    output_columns: Iterable[str],
    schema: SchemaMapping
    | MappingSchema,  # a prebuilt MappingSchema is reused as-is (avoids rebuilds)
    dialect: str = "snowflake",
) -> list[RawColumnLineage]:
    columns = list(output_columns)
    sg_schema = (
        schema if isinstance(schema, MappingSchema) else build_sqlglot_schema(schema, dialect)
    )
    try:
        parsed = sqlglot.parse_one(compiled_sql, dialect=dialect)
    except SqlglotError as e:
        return [RawColumnLineage(c, False, (), (f"parse_error: {e}",)) for c in columns]

    branches = _flatten_setops(parsed)
    is_set_op = len(branches) > 1
    if (
        is_set_op and parsed.args.get("with") is not None
    ):  # keep top-level CTEs visible to each branch
        top_with = parsed.args["with"]
        kept = []
        for b in branches:
            if b.args.get("with") is None:
                b = b.copy()
                b.set("with", top_with.copy())
            kept.append(b)
        branches = kept

    # Qualify ONCE per branch: column=None returns {OUTPUT_COL: Node} for every projection, sharing one
    # parse/qualify across all columns (vs once per column — the dominant cost on wide models).
    branch_maps: list[dict[str, Node]] = []
    parse_error: str | None = None
    for branch in branches:
        try:
            nodes = lineage(None, branch, schema=sg_schema, dialect=dialect)
            branch_maps.append({name.lower(): node for name, node in nodes.items()})
        except SqlglotError as e:
            parse_error = f"parse_error: {e}"
            branch_maps.append({})

    results: list[RawColumnLineage] = []
    for col in columns:
        sources: list[RawSource] = []
        warnings: list[str] = [parse_error] if parse_error else []
        seen: set[tuple] = set()
        found = False
        for bi, node_map in enumerate(branch_maps):
            node = node_map.get(col.lower())
            if node is None:
                continue
            found = True
            for i, path in enumerate(_paths(node)):
                if i >= _MAX_PATHS:
                    warnings.append("path_limit_reached")
                    break
                source, warning = _path_to_source(path, bi if is_set_op else None)
                if warning:
                    warnings.append(warning)
                if source is None:
                    continue
                key = (source.relation_key, source.column, source.branch_index)
                if key in seen:  # first path wins for a given (leaf, branch)
                    continue
                seen.add(key)
                sources.append(source)
        if not found and not parse_error:
            warnings.append("unresolved_column")
        results.append(
            RawColumnLineage(col, is_set_op, tuple(sources), tuple(dict.fromkeys(warnings)))
        )
    return results
