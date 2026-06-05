import typer

app = typer.Typer(help="dbt column-lineage engine")


@app.callback(invoke_without_command=True)
def main() -> None:
    pass
