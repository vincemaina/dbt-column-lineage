"""Typer CLI: extract / upstream / downstream over the lineage engine."""

from pathlib import Path

import typer

from dbt_column_lineage import serialize
from dbt_column_lineage.engine import extract_lineage
from dbt_column_lineage.graph import LineageGraph, parse_column_ref
from dbt_column_lineage.ir import LineageResult

app = typer.Typer(help="dbt column-lineage engine", no_args_is_help=True)

_MANIFEST = typer.Option(..., help="path to dbt manifest.json")
_CATALOG = typer.Option(None, help="path to dbt catalog.json (optional; omit to infer schemas)")
_SELECT = typer.Option(None, help="dbt node selector (e.g. +model, model+, path:...)")
_MODE = typer.Option("auto", "--schema-mode", help="schema source: auto | catalog | inferred")


def _warn(result: LineageResult) -> None:
    if result.warnings:
        head = "; ".join(result.warnings[:5])
        extra = "" if len(result.warnings) <= 5 else f" (+{len(result.warnings) - 5} more)"
        typer.echo(f"{len(result.warnings)} warning(s): {head}{extra}", err=True)


@app.command()
def extract(
    manifest: str = _MANIFEST,
    catalog: str = _CATALOG,
    select: str = _SELECT,
    schema_mode: str = _MODE,
    changed: str = typer.Option(None, help="hybrid: comma-separated changed model names"),
    state: str = typer.Option(None, help="hybrid: baseline manifest.json for state:modified"),
    output: str = typer.Option(None, help="write to this file instead of stdout"),
    fmt: str = typer.Option("json", "--format", help="json | mermaid"),
) -> None:
    """Extract column lineage for a project (or a selected subset)."""
    result = extract_lineage(
        manifest,
        catalog,
        schema_mode=schema_mode,
        select=select,
        changed=changed.split(",") if changed else None,
        state_manifest=state,
    )
    _warn(result)
    text = serialize.to_mermaid(result) if fmt == "mermaid" else serialize.to_json(result)
    if output:
        Path(output).write_text(text)
    else:
        typer.echo(text)


def _graph(
    manifest: str, catalog: str | None, select: str | None, schema_mode: str
) -> LineageGraph:
    result = extract_lineage(manifest, catalog, schema_mode=schema_mode, select=select)
    _warn(result)
    return LineageGraph(result.edges)


@app.command()
def upstream(
    column: str,
    manifest: str = _MANIFEST,
    catalog: str = _CATALOG,
    select: str = _SELECT,
    schema_mode: str = _MODE,
) -> None:
    """Print the transitive upstream columns of COLUMN (e.g. model.pkg.name.col)."""
    graph = _graph(manifest, catalog, select, schema_mode)
    for ref in graph.upstream(parse_column_ref(column)):
        typer.echo(str(ref))


@app.command()
def downstream(
    column: str,
    manifest: str = _MANIFEST,
    catalog: str = _CATALOG,
    select: str = _SELECT,
    schema_mode: str = _MODE,
) -> None:
    """Print the transitive downstream columns of COLUMN."""
    graph = _graph(manifest, catalog, select, schema_mode)
    for ref in graph.downstream(parse_column_ref(column)):
        typer.echo(str(ref))
