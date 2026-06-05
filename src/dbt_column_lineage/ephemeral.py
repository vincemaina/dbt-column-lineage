"""Ephemeral model re-attribution.

dbt compiles ephemeral models by INLINING them into each consumer as a CTE named
`__dbt__cte__<name>`. By default, then, a consumer's lineage traces straight through that inlined CTE
to the ephemeral's own sources, and the ephemeral never appears as a node in the graph.

We restore it. For each ephemeral model we (1) register its relation in the schema with its inferred
output columns, and (2) rewrite every consumer by STUBBING each inlined `__dbt__cte__<name>` CTE body
to `SELECT * FROM <relation>`. Lineage then stops at the ephemeral relation as a real intermediate
node, and the ephemeral is still analyzed as its own model (ephemeral -> its sources). sqlglot-facing.
"""

from sqlglot import MappingSchema, exp, parse_one
from sqlglot.errors import SqlglotError

from dbt_column_lineage.artifacts import DbtArtifacts
from dbt_column_lineage.inference import infer_output_columns
from dbt_column_lineage.schema_resolver import SchemaMapping

_CTE_PREFIX = "__dbt__cte__"


def ephemeral_cte_map(artifacts: DbtArtifacts) -> dict[str, str]:
    """`{"__dbt__cte__<name>": "<DB.SCHEMA.RELATION>"}` (CTE name lower-cased) for every ephemeral
    model — the inlined-CTE alias dbt generates, mapped to that model's relation key."""
    out: dict[str, str] = {}
    for node in artifacts.nodes.values():
        if node.resource_type == "model" and node.materialized == "ephemeral":
            out[f"{_CTE_PREFIX}{node.name}".lower()] = node.relation.key()
    return out


def ephemeral_schema(
    artifacts: DbtArtifacts, sg_schema: MappingSchema, dialect: str
) -> SchemaMapping:
    """Inferred output columns for each ephemeral relation, so consumers can resolve (and `SELECT *`)
    against the ephemeral as if it were a built table. Inference runs on the ephemeral's OWN compiled
    SQL (self-contained — its refs are already inlined), so no ordering between ephemerals is needed."""
    schema: SchemaMapping = {}
    for node in artifacts.nodes.values():
        if node.resource_type != "model" or node.materialized != "ephemeral":
            continue
        if not node.compiled_code:
            continue
        try:
            cols = infer_output_columns(node.compiled_code, sg_schema, dialect)
        except SqlglotError:
            cols = []
        if cols:
            schema[node.relation.key()] = {c.upper(): "UNKNOWN" for c in cols}
    return schema


def rewrite_ephemeral_ctes(compiled_sql: str, cte_map: dict[str, str], dialect: str) -> str:
    """Stub every inlined `__dbt__cte__<name>` CTE body to `SELECT * FROM <relation>` so lineage stops
    at the ephemeral relation. Returns the SQL unchanged if it has no ephemeral CTEs or cannot parse."""
    if not cte_map or _CTE_PREFIX not in compiled_sql:
        return compiled_sql
    try:
        tree = parse_one(compiled_sql, dialect=dialect)
    except SqlglotError:
        return compiled_sql
    changed = False
    for cte in tree.find_all(exp.CTE):
        relation = cte_map.get(cte.alias.lower())
        if relation is not None:
            cte.set("this", parse_one(f"SELECT * FROM {relation}", dialect=dialect))
            changed = True
    return tree.sql(dialect=dialect) if changed else compiled_sql
