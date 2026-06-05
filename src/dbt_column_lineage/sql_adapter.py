"""Thin adapter over SQLGlot's lineage(): for one compiled model, find each output column's upstream
base-table column contributions, the projection expression that produced them, and the structural join
context. One of only two modules that import sqlglot (the other is classify.py).

Set operations (UNION/EXCEPT/INTERSECT) are decomposed into their branch SELECTs and each branch is
processed independently — this avoids navigating sqlglot's set-op lineage tree and yields clean branch
indices. Errors are contained: a parse/lineage failure for a column yields a warned, empty-source result.
"""

from collections.abc import Iterable
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.lineage import lineage

from dbt_column_lineage.schema_resolver import SchemaMapping

_SET_OPS = tuple(
    c
    for c in (getattr(exp, n, None) for n in ("Union", "Except", "Intersect"))
    if isinstance(c, type)
)


@dataclass(frozen=True)
class RawSource:
    relation_key: str | None  # base table "DB.SCHEMA.TABLE" (UPPER), or None if unresolved
    column: str  # upstream column name as sqlglot reports it (UPPER for Snowflake)
    unresolved: bool  # True if from a "*" or "?" placeholder leaf
    projection: (
        exp.Expression | None
    )  # value expression (Alias.this) producing this column in its select
    join: tuple[str, bool] | None  # (join_type, introduces_nulls) if reached via a join, else None
    branch_index: int | None  # set-operation branch index, else None


@dataclass(frozen=True)
class RawColumnLineage:
    output_column: str
    is_set_operation: bool
    sources: tuple[RawSource, ...]
    warnings: tuple[str, ...]


def _to_sqlglot_schema(schema: SchemaMapping) -> dict:
    """Flat {relation_key: {col: type}} -> nested {db: {schema: {table: {col: type}}}}."""
    nested: dict = {}
    for key, cols in schema.items():
        parts = key.split(".")
        if len(parts) != 3:
            continue
        db, sch, tbl = parts
        nested.setdefault(db, {}).setdefault(sch, {})[tbl] = dict(cols)
    return nested


def _flatten_setops(expr: exp.Expression) -> list[exp.Expression]:
    """Branch SELECTs of a (possibly nested) set operation, left-to-right; [expr] if not a set op."""
    if isinstance(expr, _SET_OPS):
        return _flatten_setops(expr.this) + _flatten_setops(expr.expression)
    return [expr]


def _join_context(select: exp.Expression) -> tuple[str | None, dict[str, tuple[str, bool]]]:
    """Return (anchor_relation_key, {joined_relation_key: (join_type, introduces_nulls)}).

    The FROM anchor is preserved (no null introduction); a relation reached via LEFT/RIGHT/FULL join is
    the nullable side. Only handles plain table FROM/JOINs (subqueries -> no join info, degrade quietly).
    """
    anchor: str | None = None
    from_ = select.args.get("from") if isinstance(select, exp.Select) else None
    if from_ is not None and isinstance(from_.this, exp.Table):
        anchor = exp.table_name(from_.this).upper()
    joined: dict[str, tuple[str, bool]] = {}
    for join in (select.args.get("joins") or []) if isinstance(select, exp.Select) else []:
        if not isinstance(join.this, exp.Table):
            continue
        key = exp.table_name(join.this).upper()
        side = (join.args.get("side") or "").upper()
        kind = (join.args.get("kind") or "").upper()
        join_type = side or kind or "INNER"
        introduces_nulls = side in ("LEFT", "RIGHT", "FULL")
        joined[key] = (join_type, introduces_nulls)
    return anchor, joined


def extract_column_lineage(
    compiled_sql: str,
    output_columns: Iterable[str],
    schema: SchemaMapping,
    dialect: str = "snowflake",
) -> list[RawColumnLineage]:
    columns = list(output_columns)
    sg_schema = _to_sqlglot_schema(schema)
    try:
        parsed = sqlglot.parse_one(compiled_sql, dialect=dialect)
    except SqlglotError as e:
        return [RawColumnLineage(c, False, (), (f"parse_error: {e}",)) for c in columns]

    branches = _flatten_setops(parsed)
    is_set_op = len(branches) > 1

    results: list[RawColumnLineage] = []
    for col in columns:
        sources: list[RawSource] = []
        warnings: list[str] = []
        for bi, branch in enumerate(branches):
            _, joined = _join_context(branch)
            try:
                root = lineage(col, branch.sql(dialect=dialect), schema=sg_schema, dialect=dialect)
            except SqlglotError as e:
                warnings.append(f"parse_error: {e}")
                continue
            proj = root.expression
            value_expr = proj.this if isinstance(proj, exp.Alias) else proj
            branch_index = bi if is_set_op else None
            for node in root.walk():
                if node.downstream:
                    continue  # not a leaf
                if not isinstance(node.expression, exp.Table):
                    warnings.append(
                        "select_star_unresolved" if node.name == "*" else "unresolved_column"
                    )
                    sources.append(RawSource(None, node.name, True, value_expr, None, branch_index))
                    continue
                relation_key = exp.table_name(node.expression).upper()
                column = node.name.split(".")[-1]
                join = joined.get(relation_key)
                if column == "*":
                    # an unexpanded SELECT * from a real but un-schema'd table: we know the relation,
                    # not the column. Flag unresolved rather than fabricate a column named "*".
                    warnings.append("select_star_unresolved")
                    sources.append(
                        RawSource(relation_key, "*", True, value_expr, join, branch_index)
                    )
                    continue
                sources.append(
                    RawSource(relation_key, column, False, value_expr, join, branch_index)
                )
        results.append(
            RawColumnLineage(col, is_set_op, tuple(sources), tuple(dict.fromkeys(warnings)))
        )
    return results
