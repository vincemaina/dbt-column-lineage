"""Build the typed transform chain + LineageEdges for one model from the adapter's raw lineage.

Each edge's `transforms` is the ordered chain the value passes through, upstream -> downstream, spanning
EVERY CTE/subquery hop (not just the final projection): structural JOIN (row assembly) first, then each
hop's value ops / rename walked SOURCE->OUTPUT with the consumed column name threaded across renames,
then UNION (set-op branch combine) last. Facts only — no guarantee-survival reasoning. May import
sqlglot (to inspect each hop's projection AST).
"""

from sqlglot import exp

from dbt_column_lineage.artifacts import ManifestNode
from dbt_column_lineage.ir import (
    ColumnRef,
    Confidence,
    LineageEdge,
    LineageType,
    SchemaProvenance,
    SelfReference,
    SourceLocation,
    TransformKind,
    TransformStep,
)
from dbt_column_lineage.schema_resolver import SchemaResolver
from dbt_column_lineage.sql_adapter import RawColumnLineage, RawSource


def _func_name(expr: exp.Expression) -> str:
    if isinstance(expr, exp.Anonymous):
        return str(expr.this).upper()
    if isinstance(expr, exp.Func):
        try:
            return expr.sql_name().upper()
        except Exception:  # noqa: BLE001 - defensive: fall back to the class name
            return type(expr).__name__.upper()
    return type(expr).__name__.upper()


def _find_column(expr: exp.Expression, name: str) -> exp.Column | None:
    for col in expr.find_all(exp.Column):
        if col.name.upper() == name.upper():
            return col
    return None


def _contains(expr: exp.Expression, target: exp.Expression) -> bool:
    return any(n is target for n in expr.find_all(type(target)))


def _window_role(window: exp.Window, col_node: exp.Column) -> str:
    """partition_by / order_by / value, by which window arg-subtree the column sits in."""
    node: exp.Expression | None = col_node
    while node is not None and node.parent is not window:
        node = node.parent
    key = node.arg_key if node is not None else None
    if key == "partition_by":
        return "partition_by"
    if key == "order":
        return "order_by"
    return "value"


def _coalesce_default(node: exp.Coalesce, col_node: exp.Column) -> str:
    parts = [node.this, *(node.args.get("expressions") or [])]
    others = [
        p.sql(dialect="snowflake")
        for p in parts
        if p is not col_node and not _contains(p, col_node)
    ]
    return ", ".join(others)


def _op_step(node: exp.Expression, col_node: exp.Column) -> TransformStep | None:
    if isinstance(node, exp.Cast):
        return TransformStep(TransformKind.CAST, {"to_type": node.to.sql(dialect="snowflake")})
    if isinstance(node, exp.Coalesce):
        return TransformStep(TransformKind.COALESCE, {"default": _coalesce_default(node, col_node)})
    if isinstance(node, exp.Case):
        return TransformStep(TransformKind.CASE)
    if isinstance(node, exp.Window):
        return TransformStep(
            TransformKind.WINDOW,
            {"func": _func_name(node.this), "role": _window_role(node, col_node)},
        )
    if isinstance(node, exp.AggFunc):
        return TransformStep(TransformKind.AGGREGATION, {"func": _func_name(node)})
    if isinstance(node, (exp.Func, exp.Binary)):
        return TransformStep(TransformKind.EXPRESSION)
    return None  # structural wrapper (Alias, Paren, Ordered, Order, Column, ...) — not a value op


def _ancestors_within(node: exp.Expression, top: exp.Expression):
    cur = node.parent
    while cur is not None:
        yield cur
        if cur is top:
            return
        cur = cur.parent


def _value_steps(projection: exp.Expression | None, upstream_column: str) -> list[TransformStep]:
    if projection is None or isinstance(projection, exp.Column):
        return []  # pure passthrough — naming is added by the caller
    col_node = _find_column(projection, upstream_column)
    if col_node is None:
        return [TransformStep(TransformKind.UNKNOWN)]
    # Collapse CASE-internal ops: a column inside a CASE (e.g. a WHEN condition) contributes a single
    # CASE step, not the comparison machinery (=, If) within it. Only ops wrapping the CASE decompose.
    start: exp.Expression = col_node
    steps: list[TransformStep] = []
    for ancestor in _ancestors_within(col_node, projection):
        if isinstance(ancestor, exp.Case):
            start = ancestor
            steps.append(TransformStep(TransformKind.CASE))
            break
    node: exp.Expression | None = start.parent if start is not col_node else col_node.parent
    while node is not None:
        step = _op_step(node, col_node)
        if step is not None:
            steps.append(step)
        if node is projection or start is projection:
            break
        node = node.parent
    return steps


def build_transform_chain(source: RawSource, output_column: str) -> tuple[TransformStep, ...]:
    """Assemble the ordered chain across every hop. The structural JOIN (source side) goes first; then
    each hop's value ops / rename, walking SOURCE->OUTPUT; the consumed column name is threaded forward
    so it tracks renames across CTEs. A set-op branch marker goes last."""
    steps: list[TransformStep] = []
    input_col = source.column
    for hop in source.hops:  # deepest (source) -> root (output)
        if hop.join is not None:  # a join at THIS hop (incl. joins above the source hop)
            join_type, introduces_nulls = hop.join
            steps.append(
                TransformStep(
                    TransformKind.JOIN,
                    {"join_type": join_type, "introduces_nulls": introduces_nulls},
                )
            )
        expr = hop.expression
        value = expr.this if isinstance(expr, exp.Alias) else expr
        out_name = (
            expr.alias_or_name if isinstance(expr, exp.Alias) else getattr(value, "name", input_col)
        )
        if isinstance(value, exp.Column):  # passthrough at this hop
            if input_col.lower() == out_name.lower():
                steps.append(TransformStep(TransformKind.IDENTITY))
            else:
                steps.append(
                    TransformStep(
                        TransformKind.RENAME, {"from": input_col.lower(), "to": out_name.lower()}
                    )
                )
        else:
            hop_steps = _value_steps(value, input_col)
            steps.extend(hop_steps or [TransformStep(TransformKind.UNKNOWN)])
        input_col = out_name
    if source.branch_index is not None:
        steps.append(TransformStep(TransformKind.UNION, {"branch": source.branch_index}))
    if not steps:
        steps.append(TransformStep(TransformKind.UNKNOWN))
    return tuple(steps)


def build_model_edges(
    node: ManifestNode,
    raw_lineage: list[RawColumnLineage],
    relation_to_uid: dict[str, str],
    resolver: SchemaResolver,
    dialect: str = "snowflake",
) -> tuple[list[LineageEdge], list[str], list[SelfReference]]:
    edges: list[LineageEdge] = []
    warnings: list[str] = []
    self_refs: list[SelfReference] = []
    location = SourceLocation(node.original_file_path, node.unique_id)
    for rcl in raw_lineage:
        warnings.extend(rcl.warnings)
        for source in rcl.sources:
            if source.relation_key is None:
                continue  # unresolved leaves are warned, never turned into a fabricated edge
            up_uid = relation_to_uid.get(source.relation_key)
            if up_uid is None:
                warnings.append(f"unmapped_relation:{source.relation_key}")
                continue
            if up_uid == node.unique_id:
                self_refs.append(
                    SelfReference(node.unique_id, rcl.output_column.lower(), source.column.lower())
                )
                continue  # self-reference (incremental `{{ this }}`) — captured, not a value edge
            provenance = resolver.provenance(source.relation_key)
            confidence = (
                Confidence.HIGH if provenance == SchemaProvenance.CATALOG else Confidence.LOW
            )
            expression = source.hops[-1].expression.sql(dialect=dialect) if source.hops else None
            edges.append(
                LineageEdge(
                    downstream=ColumnRef(node.unique_id, rcl.output_column.lower()),
                    upstream=ColumnRef(up_uid, source.column.lower()),
                    lineage_type=LineageType.DIRECT,
                    transforms=build_transform_chain(source, rcl.output_column),
                    expression=expression,
                    schema_provenance=provenance,
                    confidence=confidence,
                    dialect=dialect,
                    source_location=location,
                )
            )
    return edges, list(dict.fromkeys(warnings)), self_refs
