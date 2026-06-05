import json
from pathlib import Path

from typer.testing import CliRunner

from dbt_column_lineage.cli import app

FIXTURE = Path(__file__).parent / "fixtures" / "jaffle"
MANIFEST = str(FIXTURE / "manifest.json")
CATALOG = str(FIXTURE / "catalog.json")
runner = CliRunner()


def test_help_works():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "extract" in result.stdout


def test_extract_json():
    result = runner.invoke(app, ["extract", "--manifest", MANIFEST, "--catalog", CATALOG])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data["edges"]) == 26
    assert len(data["processed_assets"]) == 7


def test_extract_mermaid():
    result = runner.invoke(
        app, ["extract", "--manifest", MANIFEST, "--catalog", CATALOG, "--format", "mermaid"]
    )
    assert result.exit_code == 0
    assert result.stdout.lstrip().startswith("flowchart TD")


def test_extract_to_file(tmp_path):
    out = tmp_path / "lineage.json"
    result = runner.invoke(
        app, ["extract", "--manifest", MANIFEST, "--catalog", CATALOG, "--output", str(out)]
    )
    assert result.exit_code == 0
    assert len(json.loads(out.read_text())["edges"]) == 26


def test_upstream_command():
    result = runner.invoke(
        app,
        [
            "upstream",
            "model.jaffle.customers.lifetime_value",
            "--manifest",
            MANIFEST,
            "--catalog",
            CATALOG,
        ],
    )
    assert result.exit_code == 0
    assert "model.jaffle.stg_orders.amount" in result.stdout
    assert "source.jaffle.raw.raw_orders.amount" in result.stdout


def test_downstream_command():
    result = runner.invoke(
        app,
        [
            "downstream",
            "source.jaffle.raw.raw_orders.amount",
            "--manifest",
            MANIFEST,
            "--catalog",
            CATALOG,
        ],
    )
    assert result.exit_code == 0
    assert "model.jaffle.customers.lifetime_value" in result.stdout
