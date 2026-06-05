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
    ControlCategory,
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


def _coalesce_default(node: exp.Coalesce, col_node: exp.Column, dialect: str) -> str:
    parts = [node.this, *(node.args.get("expressions") or [])]
    others = [
        p.sql(dialect=dialect) for p in parts if p is not col_node and not _contains(p, col_node)
    ]
    return ", ".join(others)


def _coalesce_position(node: exp.Coalesce, col_node: exp.Column) -> dict[str, int]:
    """Which COALESCE argument the column occupies, and the total count — makes the sibling
    (alternatives) relationship explicit and ordered (#5)."""
    parts = [node.this, *(node.args.get("expressions") or [])]
    for i, p in enumerate(parts):
        if p is col_node or _contains(p, col_node):
            return {"arg_index": i, "arg_count": len(parts)}
    return {"arg_count": len(parts)}


def _json_path(node: exp.Expression) -> str:
    """The key path / index of a variant-or-array access, e.g. 'user.id' for v:user:id, 'k' for v['k']."""
    if isinstance(node, exp.Bracket):
        return ".".join(str(e.name or e.sql()) for e in node.expressions)
    path = node.args.get("expression")
    if isinstance(path, exp.JSONPath):
        keys = [str(k.this) for k in path.expressions if isinstance(k, exp.JSONPathKey)]
        return ".".join(keys)
    return ""


def _case_detail(case: exp.Case) -> dict[str, bool]:
    """`else_null` = the CASE can yield NULL for unmatched rows (no ELSE, or `ELSE NULL`) — a
    null-introduction fact the test-lineage tool needs for not_null reasoning."""
    default = case.args.get("default")
    return {"else_null": default is None or isinstance(default, exp.Null)}


def _op_step(node: exp.Expression, col_node: exp.Column, dialect: str) -> TransformStep | None:
    if isinstance(node, exp.Cast):  # exp.Cast also matches TryCast (safe=True)
        detail: dict[str, str | int | bool] = {"to_type": node.to.sql(dialect=dialect)}
        if node.args.get("safe"):  # TRY_CAST: yields NULL on conversion failure (CAST errors instead)
            detail["safe"] = True
        return TransformStep(TransformKind.CAST, detail)
    if isinstance(node, exp.Coalesce):
        detail = {"default": _coalesce_default(node, col_node, dialect)}
        detail.update(_coalesce_position(node, col_node))
        return TransformStep(TransformKind.COALESCE, detail)
    if isinstance(node, exp.Case):
        return TransformStep(TransformKind.CASE, _case_detail(node))
    if isinstance(node, exp.Window):
        detail = {"func": _func_name(node.this), "role": _window_role(node, col_node)}
        spec = node.args.get("spec")
        if spec is not None:  # ROWS/RANGE frame affects which rows feed the value
            detail["frame"] = spec.sql(dialect=dialect)
        return TransformStep(TransformKind.WINDOW, detail)
    if isinstance(node, exp.AggFunc):
        detail = {"func": _func_name(node)}
        if isinstance(node.this, exp.Distinct):  # COUNT(DISTINCT x) etc. — dedup semantics
            detail["distinct"] = True
        return TransformStep(TransformKind.AGGREGATION, detail)
    if isinstance(node, (exp.JSONExtract, exp.JSONExtractScalar, exp.Bracket)):
        path = _json_path(node)
        return TransformStep(TransformKind.STRUCT_ACCESS, {"path": path} if path else {})
    if isinstance(node, exp.Nullif):  # NULLIF(x, y): NULL when x = y -> introduces nulls
        return TransformStep(TransformKind.EXPRESSION, {"func": "NULLIF", "introduces_nulls": True})
    if isinstance(node, exp.Binary):  # arithmetic / other binary op — record the operator
        return TransformStep(TransformKind.EXPRESSION, {"op": node.key})
    if isinstance(node, exp.Func):  # named scalar function — record its name
        return TransformStep(TransformKind.EXPRESSION, {"func": _func_name(node)})
    return None  # structural wrapper (Alias, Paren, Ordered, Order, Column, ...) — not a value op


def _ancestors_within(node: exp.Expression, top: exp.Expression):
    cur = node.parent
    while cur is not None:
        yield cur
        if cur is top:
            return
        cur = cur.parent


def _value_steps(
    projection: exp.Expression | None, upstream_column: str, dialect: str
) -> list[TransformStep]:
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
            steps.append(TransformStep(TransformKind.CASE, _case_detail(ancestor)))
            break
    node: exp.Expression | None = start.parent if start is not col_node else col_node.parent
    while node is not None:
        step = _op_step(node, col_node, dialect)
        if step is not None:
            steps.append(step)
        if node is projection or start is projection:
            break
        node = node.parent
    return steps


def build_transform_chain(
    source: RawSource, output_column: str, dialect: str = "snowflake"
) -> tuple[TransformStep, ...]:
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
        elif isinstance(value, exp.Identifier):
            # a bare identifier hop is sqlglot's representation of a table-function pseudo-column
            # (LATERAL FLATTEN / explode output: VALUE, SEQ, KEY, ...) — a row-exploding UNNEST
            steps.append(TransformStep(TransformKind.UNNEST, {"output": value.name}))
        else:
            hop_steps = _value_steps(value, input_col, dialect)
            steps.extend(hop_steps or [TransformStep(TransformKind.UNKNOWN)])
        input_col = out_name
    if source.branch_index is not None:
        steps.append(TransformStep(TransformKind.UNION, {"branch": source.branch_index}))
    if not steps:
        steps.append(TransformStep(TransformKind.UNKNOWN))
    return tuple(steps)


def _is_within(container: exp.Expression, node: exp.Expression) -> bool:
    return node is container or any(n is node for n in container.find_all(type(node)))


def _control_role(value_expr: exp.Expression, column_name: str) -> ControlCategory | None:
    """If the column influences the output as CONTROL (window partition/order key, or a CASE WHEN
    condition) rather than contributing its value, return the control category; else None."""
    col_node = _find_column(value_expr, column_name)
    if col_node is None:
        return None
    window = col_node.find_ancestor(exp.Window)
    if window is not None and _is_within(value_expr, window):
        if _window_role(window, col_node) in ("partition_by", "order_by"):
            return ControlCategory.WINDOW_PARTITION
    case = col_node.find_ancestor(exp.Case)
    if case is not None and _is_within(value_expr, case):
        for branch in case.args.get("ifs") or []:
            condition = branch.this
            if condition is not None and any(c is col_node for c in condition.find_all(exp.Column)):
                return ControlCategory.CONDITIONAL
    return None


def _influence_category(source: RawSource) -> ControlCategory | None:
    """Walk the hops (threading the consumed column) and report a control role if the column is used as
    a window partition/order key or a CASE condition at any hop, else None (= value)."""
    input_col = source.column
    for hop in source.hops:
        expr = hop.expression
        value = expr.this if isinstance(expr, exp.Alias) else expr
        out_name = (
            expr.alias_or_name if isinstance(expr, exp.Alias) else getattr(value, "name", input_col)
        )
        if not isinstance(value, exp.Column):
            role = _control_role(value, input_col)
            if role is not None:
                return role
        input_col = out_name
    return None


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
            downstream = ColumnRef(node.unique_id, rcl.output_column.lower())
            upstream = ColumnRef(up_uid, source.column.lower())
            role = _influence_category(source)
            if role is not None:  # control influence -> column-level INDIRECT edge (no value chain)
                edges.append(
                    LineageEdge(
                        downstream,
                        upstream,
                        LineageType.INDIRECT,
                        (),
                        control=role,
                        expression=expression,
                        schema_provenance=provenance,
                        confidence=confidence,
                        dialect=dialect,
                        source_location=location,
                    )
                )
            else:
                edges.append(
                    LineageEdge(
                        downstream,
                        upstream,
                        LineageType.DIRECT,
                        build_transform_chain(source, rcl.output_column, dialect),
                        expression=expression,
                        schema_provenance=provenance,
                        confidence=confidence,
                        dialect=dialect,
                        source_location=location,
                    )
                )
    return edges, list(dict.fromkeys(warnings)), self_refs
