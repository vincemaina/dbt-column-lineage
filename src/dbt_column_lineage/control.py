"""Control / INDIRECT lineage: columns that INFLUENCE a model's rows without flowing into a value —
join keys, filter predicates (WHERE/HAVING/QUALIFY), and group-by / sort columns. SQLGlot's lineage()
deliberately ignores these. Resolved to base source columns through CTEs via SQLGlot's scope tree.

Model-level: a filter/group-by affects ALL output columns, so each control column is recorded once per
model (not per output column). sqlglot-facing.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlglot import MappingSchema, exp, parse_one
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import Scope, build_scope

from dbt_column_lineage.ir import ControlCategory
from dbt_column_lineage.schema_resolver import SchemaMapping
from dbt_column_lineage.sql_adapter import build_sqlglot_schema

_OUTER_JOINS = frozenset({"LEFT", "RIGHT", "FULL"})


@dataclass(frozen=True)
class RawControl:
    category: ControlCategory
    relation_key: str  # base relation (UPPER "DB.SCHEMA.TABLE")
    column: str  # base column (UPPER)


@dataclass(frozen=True)
class RawOperations:
    """Model-grain operation facts (no asset; the engine binds it). Constructs present in the compiled
    SQL that bear on cardinality / nullability — facts only."""

    joins: tuple[str, ...]  # each join's type (any scope): INNER|LEFT|RIGHT|FULL|CROSS
    set_operation: str | None  # top-level combine label, else None
    grouped: bool
    distinct: bool
    lateral_flatten: bool
    grain: tuple[str, ...]  # output column names of the final GROUP BY grain (the unique key it
    # forms), lower-cased; () unless EVERY group-by key maps to an output column (else the output
    # has no clean grain key). A consumer can treat this tuple as a unique key of the model's rows.

    @property
    def may_multiply_rows(self) -> bool:
        has_union_all = self.set_operation == "UNION ALL"
        return bool(self.joins) or has_union_all or self.lateral_flatten

    @property
    def may_introduce_nulls(self) -> bool:
        return any(j in _OUTER_JOINS for j in self.joins)


def _resolve_to_base(scope: Scope, column: exp.Column) -> list[tuple[str, str]]:
    """Resolve a (qualified) column to its base-table source column(s), tracing through CTE scopes."""
    table = column.table
    if not table:
        return []
    source = scope.sources.get(table)
    if isinstance(source, exp.Table):
        return [(exp.table_name(source).upper(), column.name.upper())]
    if isinstance(source, Scope) and isinstance(source.expression, exp.Select):
        out: list[tuple[str, str]] = []
        for projection in source.expression.selects:
            if projection.alias_or_name.upper() == column.name.upper():
                for col in projection.find_all(exp.Column):
                    out.extend(_resolve_to_base(source, col))
        return out
    return []


def _clause_columns(node: exp.Expression | None) -> Iterable[exp.Column]:
    return node.find_all(exp.Column) if node is not None else ()


def _positional(select: exp.Select, expr: exp.Expression) -> Iterable[exp.Column]:
    """Resolve `GROUP BY 1` / `ORDER BY 2` to the referenced projection's columns; else the columns."""
    if isinstance(expr, exp.Literal) and expr.is_int:
        index = int(expr.name) - 1
        if 0 <= index < len(select.selects):
            yield from select.selects[index].find_all(exp.Column)
    else:
        yield from expr.find_all(exp.Column)


def _group_columns(select: exp.Select) -> Iterable[exp.Column]:
    group = select.args.get("group")
    if group is None:
        return
    if group.args.get("all"):  # `GROUP BY ALL` -> every non-aggregate select expression is a key
        for projection in select.selects:
            value = projection.this if isinstance(projection, exp.Alias) else projection
            if not list(value.find_all(exp.AggFunc)):
                yield from value.find_all(exp.Column)
        return
    for expr in group.expressions:
        yield from _positional(select, expr)


def _order_columns(select: exp.Select) -> Iterable[exp.Column]:
    order = select.args.get("order")
    for ordered in order.expressions if order else ():
        target = ordered.this if isinstance(ordered, exp.Ordered) else ordered
        yield from _positional(select, target)


def extract_controls(
    compiled_sql: str, schema: SchemaMapping | MappingSchema, dialect: str = "snowflake"
) -> list[RawControl]:
    sg_schema = (
        schema if isinstance(schema, MappingSchema) else build_sqlglot_schema(schema, dialect)
    )
    try:
        qualified = qualify(
            parse_one(compiled_sql, dialect=dialect),
            schema=sg_schema,
            dialect=dialect,
            validate_qualify_columns=False,
        )
        root = build_scope(qualified)
    except SqlglotError:
        return []
    if root is None:
        return []

    seen: set[tuple] = set()
    controls: list[RawControl] = []

    def add(category: ControlCategory, scope: Scope, columns: Iterable[exp.Column]) -> None:
        for col in columns:
            for relation, column in _resolve_to_base(scope, col):
                key = (category, relation, column)
                if key not in seen:
                    seen.add(key)
                    controls.append(RawControl(category, relation, column))

    for scope in root.traverse():
        select = scope.expression
        if not isinstance(select, exp.Select):
            continue
        add(ControlCategory.FILTER, scope, _clause_columns(select.args.get("where")))
        add(ControlCategory.FILTER, scope, _clause_columns(select.args.get("having")))
        add(ControlCategory.FILTER, scope, _clause_columns(select.args.get("qualify")))
        add(ControlCategory.GROUP_BY, scope, _group_columns(select))
        add(ControlCategory.SORT, scope, _order_columns(select))
        for join in select.args.get("joins") or []:
            add(ControlCategory.JOIN, scope, _clause_columns(join.args.get("on")))
    return controls


def reads_from_stage(compiled_sql: str, dialect: str = "snowflake") -> bool:
    """True if the model reads from a Snowflake external stage (`FROM @stage`). Such models are root
    ingestion points with no upstream dbt asset — 0 lineage edges is correct, not an error. Gated on a
    cheap substring check so the parse is skipped for the ~99% of models without stages."""
    if "@" not in compiled_sql:
        return False
    try:
        tree = parse_one(compiled_sql, dialect=dialect)
    except SqlglotError:
        return False
    return any(t.sql(dialect=dialect).lstrip().startswith("@") for t in tree.find_all(exp.Table))


def _join_type(join: exp.Join) -> str:
    side = (join.args.get("side") or "").upper()
    kind = (join.args.get("kind") or "").upper()
    return side or kind or "INNER"


def _set_op_label(node: exp.Expression) -> str | None:
    """Top-level set-operation label describing the model's final combine, else None."""
    if isinstance(node, exp.Union):  # Except/Intersect subclass Union in sqlglot
        if isinstance(node, exp.Except):
            return "EXCEPT"
        if isinstance(node, exp.Intersect):
            return "INTERSECT"
        return "UNION" if node.args.get("distinct") else "UNION ALL"
    return None


def _output_grain(select: exp.Select) -> tuple[str, ...]:
    """The GROUP BY grain of `select` as OUTPUT column names — the unique key the grouping forms. Maps
    each group-by key (positional `group by 1,2`, or by-expression) to the projection that selects it.
    Returns () if any key is not selected (then the output has no clean grain key) or for GROUP BY ALL."""
    group = select.args.get("group")
    if group is None or group.args.get("all"):
        return ()
    outs = select.selects
    by_sql = {(o.this if isinstance(o, exp.Alias) else o).sql(): o.alias_or_name for o in outs}
    names: list[str] = []
    for key in group.expressions:
        if isinstance(key, exp.Literal) and key.is_int:
            i = int(key.name) - 1
            if not 0 <= i < len(outs):
                return ()
            names.append(outs[i].alias_or_name)
        else:
            name = by_sql.get(key.sql())
            if name is None:  # a grouped key that isn't selected -> no clean output grain
                return ()
            names.append(name)
    return tuple(n.lower() for n in names if n)


def extract_operations(
    compiled_sql: str, dialect: str = "snowflake"
) -> RawOperations | None:
    """Model-grain operation facts from compiled SQL. Structural only (no schema needed): joins (all
    scopes), the top-level set operation, GROUP BY / DISTINCT, lateral-flatten, and the output grain.
    Returns None if the SQL cannot be parsed (the engine warns elsewhere)."""
    try:
        parsed = parse_one(compiled_sql, dialect=dialect)
    except SqlglotError:
        return None
    joins = tuple(_join_type(j) for j in parsed.find_all(exp.Join))
    grouped = any(s.args.get("group") for s in parsed.find_all(exp.Select))
    distinct = any(s.args.get("distinct") for s in parsed.find_all(exp.Select))
    lateral_flatten = any(parsed.find_all(exp.Lateral)) or any(parsed.find_all(exp.Explode))
    grain = _output_grain(parsed) if isinstance(parsed, exp.Select) else ()
    return RawOperations(
        joins=joins,
        set_operation=_set_op_label(parsed),
        grouped=grouped,
        distinct=distinct,
        lateral_flatten=lateral_flatten,
        grain=grain,
    )
