"""Evaluation harness: curated Snowflake SQL patterns with HAND-VERIFIED expected column lineage,
scored for edge precision/recall and transform-chain accuracy. Ground truth is authored by reading the
SQL (independent of the engine), so this measures real correctness, not self-consistency.

Run standalone for a report:  uv run python tests/eval_harness.py
Regression gate:              tests/test_eval.py
"""

from dataclasses import dataclass

from dbt_column_lineage.classify import build_transform_chain
from dbt_column_lineage.sql_adapter import build_sqlglot_schema, extract_column_lineage


@dataclass(frozen=True)
class Case:
    name: str
    sql: str
    schema: dict  # relation_key -> {COL: type}
    expected: tuple  # (out_col, up_relation_key, up_col_lower, (kind, ...))


CASES: list[Case] = [
    Case(
        "rename_cast_identity",
        "select id as oid, cast(amt as number(38, 2)) as amt2, name from DB.S.A",
        {"DB.S.A": {"ID": "NUMBER", "AMT": "NUMBER", "NAME": "VARCHAR"}},
        (
            ("oid", "DB.S.A", "id", ("RENAME",)),
            ("amt2", "DB.S.A", "amt", ("CAST",)),
            ("name", "DB.S.A", "name", ("IDENTITY",)),
        ),
    ),
    Case(
        "coalesce",
        "select coalesce(name, 'x') as nm from DB.S.A",
        {"DB.S.A": {"NAME": "VARCHAR"}},
        (("nm", "DB.S.A", "name", ("COALESCE",)),),
    ),
    Case(
        "left_join_aggregate",
        "select a.id as id, count(b.x) as c from DB.S.A a "
        "left join DB.S.B b on a.id = b.aid group by 1",
        {"DB.S.A": {"ID": "NUMBER"}, "DB.S.B": {"X": "NUMBER", "AID": "NUMBER"}},
        (
            ("id", "DB.S.A", "id", ("IDENTITY",)),
            ("c", "DB.S.B", "x", ("JOIN", "AGGREGATION")),
        ),
    ),
    Case(
        "window_partition_and_order",
        "select id, row_number() over (partition by gid order by ts) as rn from DB.S.A",
        {"DB.S.A": {"ID": "NUMBER", "GID": "NUMBER", "TS": "TIMESTAMP"}},
        (
            ("id", "DB.S.A", "id", ("IDENTITY",)),
            ("rn", "DB.S.A", "gid", ("WINDOW",)),
            ("rn", "DB.S.A", "ts", ("WINDOW",)),
        ),
    ),
    Case(
        "union_all",
        "select x as v from DB.S.A union all select y as v from DB.S.B",
        {"DB.S.A": {"X": "NUMBER"}, "DB.S.B": {"Y": "NUMBER"}},
        (
            ("v", "DB.S.A", "x", ("RENAME", "UNION")),
            ("v", "DB.S.B", "y", ("RENAME", "UNION")),
        ),
    ),
    Case(
        "multi_cte_rename_then_aggregate",
        "with c as (select amt as renamed from DB.S.A) select sum(renamed) as total from c",
        {"DB.S.A": {"AMT": "NUMBER"}},
        (("total", "DB.S.A", "amt", ("RENAME", "AGGREGATION")),),
    ),
    Case(
        "case_expression",
        "select case when flag = 1 then 'y' else 'n' end as f from DB.S.A",
        {"DB.S.A": {"FLAG": "NUMBER"}},
        (("f", "DB.S.A", "flag", ("CASE",)),),
    ),
    Case(
        "nested_scalar_functions",
        "select upper(trim(name)) as n from DB.S.A",
        {"DB.S.A": {"NAME": "VARCHAR"}},
        (("n", "DB.S.A", "name", ("EXPRESSION", "EXPRESSION")),),
    ),
]


def _produced(case: Case) -> dict:
    out_cols = sorted({e[0] for e in case.expected})
    sg = build_sqlglot_schema(case.schema)
    edges: dict = {}
    for rcl in extract_column_lineage(case.sql, out_cols, sg):
        for src in rcl.sources:
            if src.relation_key is None:
                continue
            kinds = tuple(s.kind.value for s in build_transform_chain(src, rcl.output_column))
            edges[(rcl.output_column, src.relation_key, src.column.lower())] = kinds
    return edges


def evaluate(case: Case) -> dict:
    produced = _produced(case)
    expected = {(o, r, c): tuple(k) for (o, r, c, k) in case.expected}
    p, e = set(produced), set(expected)
    matched = p & e
    return {
        "precision": len(matched) / len(p) if p else 1.0,
        "recall": len(matched) / len(e) if e else 1.0,
        "chain_acc": (
            sum(produced[k] == expected[k] for k in matched) / len(matched) if matched else 1.0
        ),
        "missing": sorted(e - p),
        "extra": sorted(p - e),
        "chain_mismatch": [
            (k, produced[k], expected[k]) for k in matched if produced[k] != expected[k]
        ],
    }


def run() -> dict:
    return {c.name: evaluate(c) for c in CASES}


def repo_invariants(manifest_path: str, catalog_path: str, limit: int = 50) -> dict:
    """Unlabeled health metrics on a real repo (no ground truth needed): every edge's upstream should be
    a declared dbt dependency; report off-graph and UNKNOWN-chain rates. A reusable accuracy probe."""
    import json

    from dbt_column_lineage.engine import extract_lineage
    from dbt_column_lineage.ir import TransformKind

    manifest = json.loads(open(manifest_path).read())
    parent_map = manifest["parent_map"]
    cataloged = set(json.loads(open(catalog_path).read())["nodes"])
    models = [
        node["name"]
        for uid, node in manifest["nodes"].items()
        if node.get("resource_type") == "model"
        and node.get("compiled_code")
        and uid in cataloged
        and "json_flat" not in node["name"]
    ][:limit]
    total = off = unknown = 0
    for name in models:
        for edge in extract_lineage(manifest_path, catalog_path, select=name).edges:
            total += 1
            if edge.upstream.asset not in set(parent_map.get(edge.downstream.asset, ())):
                off += 1
            if any(step.kind == TransformKind.UNKNOWN for step in edge.transforms):
                unknown += 1
    return {
        "models": len(models),
        "edges": total,
        "off_dependency_graph_pct": round(100 * off / max(total, 1), 2),
        "unknown_chain_pct": round(100 * unknown / max(total, 1), 2),
    }


def main() -> None:
    results = run()
    print(f"{'case':36} {'prec':>5} {'recall':>7} {'chain':>6}")
    for name, m in results.items():
        print(f"{name:36} {m['precision']:5.2f} {m['recall']:7.2f} {m['chain_acc']:6.2f}")
        for miss in m["missing"]:
            print(f"    MISSING {miss}")
        for extra in m["extra"]:
            print(f"    EXTRA   {extra}")
        for k, got, want in m["chain_mismatch"]:
            print(f"    CHAIN   {k}: got {got} want {want}")
    n = len(results)
    print(
        f"\nAGGREGATE  precision={sum(m['precision'] for m in results.values()) / n:.3f}  "
        f"recall={sum(m['recall'] for m in results.values()) / n:.3f}  "
        f"chain={sum(m['chain_acc'] for m in results.values()) / n:.3f}  ({n} cases)"
    )


if __name__ == "__main__":
    main()
