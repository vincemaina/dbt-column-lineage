"""Typer CLI: extract / upstream / downstream over the lineage engine."""

from pathlib import Path

import typer

from dbt_column_lineage import serialize
from dbt_column_lineage.engine import extract_lineage
from dbt_column_lineage.graph import LineageGraph, parse_column_ref
from dbt_column_lineage.ir import LineageResult

app = typer.Typer(help="dbt column-lineage engine", no_args_is_help=True)

_MANIFEST = typer.Option(..., help="path to dbt manifest.json")
_CATALOG = typer.Option(..., help="path to dbt catalog.json")
_SELECT = typer.Option(None, help="dbt node selector (e.g. +model, model+, path:...)")


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
    output: str = typer.Option(None, help="write to this file instead of stdout"),
    fmt: str = typer.Option("json", "--format", help="json | mermaid"),
) -> None:
    """Extract column lineage for a project (or a selected subset)."""
    result = extract_lineage(manifest, catalog, select=select)
    _warn(result)
    text = serialize.to_mermaid(result) if fmt == "mermaid" else serialize.to_json(result)
    if output:
        Path(output).write_text(text)
    else:
        typer.echo(text)


def _graph(manifest: str, catalog: str, select: str | None) -> LineageGraph:
    result = extract_lineage(manifest, catalog, select=select)
    _warn(result)
    return LineageGraph(result.edges)


@app.command()
def upstream(
    column: str,
    manifest: str = _MANIFEST,
    catalog: str = _CATALOG,
    select: str = _SELECT,
) -> None:
    """Print the transitive upstream columns of COLUMN (e.g. model.pkg.name.col)."""
    graph = _graph(manifest, catalog, select)
    for ref in graph.upstream(parse_column_ref(column)):
        typer.echo(str(ref))


@app.command()
def downstream(
    column: str,
    manifest: str = _MANIFEST,
    catalog: str = _CATALOG,
    select: str = _SELECT,
) -> None:
    """Print the transitive downstream columns of COLUMN."""
    graph = _graph(manifest, catalog, select)
    for ref in graph.downstream(parse_column_ref(column)):
        typer.echo(str(ref))
