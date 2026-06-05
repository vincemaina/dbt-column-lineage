# Task 01 — Package scaffold & tooling

**Review gate:** no · **Prerequisites:** none · **Status:** see [CHECKLIST](./CHECKLIST.md)

## Objective

Create the Python package skeleton, dependency/tooling setup, and a working (empty) CLI entrypoint, so
every later task has a place to put code and a way to run tests and lint.

## Context

Read first: [`../architecture.md`](../architecture.md) §9 (Stack). Stack is fixed: **Python 3.12 ·
`uv` · `pytest` · `Typer` · `sqlglot[rs]`**, `src/` layout. Do not deviate.

## Files to create

```
pyproject.toml                       # update existing: deps, scripts, tool config
src/dbt_column_lineage/__init__.py    # package marker; __version__ = "0.1.0"
src/dbt_column_lineage/cli.py         # minimal Typer app named `app`, NO subcommands yet
src/dbt_column_lineage/CLAUDE.md      # folder index (will grow as modules are added)
tests/__init__.py
tests/test_smoke.py                   # imports the package, asserts __version__
.github/workflows/ci.yml              # runs uv sync + ruff + pytest on Python 3.12
```

## Requirements

1. **Dependencies** — add via uv so versions resolve and pin into `pyproject.toml`:
   - runtime: `uv add "sqlglot[rs]"` and `uv add typer`
   - dev: `uv add --dev pytest ruff`
   - **Record the exact resolved `sqlglot` version** in the CHECKLIST notes (later tasks pin to it).
2. **`pyproject.toml`**:
   - `[project]` keeps `name = "dbt-column-lineage"`, `requires-python = ">=3.12"`.
   - Add `[project.scripts]`: `dbt-column-lineage = "dbt_column_lineage.cli:app"`.
   - Configure the build backend for a `src/` layout (use `hatchling` or `uv_build` — whichever `uv`
     defaults to; the package dir is `src/dbt_column_lineage`).
   - Add `[tool.ruff]` (line length 100) and `[tool.pytest.ini_options]` (`testpaths = ["tests"]`).
3. **`cli.py`** — define `app = typer.Typer(help="dbt column-lineage engine")`. No commands yet (they
   arrive in task 11). It must be importable and `--help` must work.
4. **`src/dbt_column_lineage/CLAUDE.md`** — one-paragraph purpose + a "Modules" list (just `cli.py`,
   `__init__.py` for now). Note that later tasks add `ir.py`, `artifacts.py`, etc.
5. **CI** — `ci.yml`: on push/PR, set up Python 3.12, install `uv`, `uv sync`, run
   `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`.

## Verify

```bash
uv sync
uv run pytest                         # test_smoke passes
uv run ruff check .                   # clean
uv run ruff format --check .          # clean
uv run dbt-column-lineage --help      # prints Typer help, exit 0
```

## Acceptance criteria

- [ ] `uv sync` installs the four dependencies; resolved `sqlglot` version recorded in CHECKLIST notes.
- [ ] `import dbt_column_lineage` works and exposes `__version__ == "0.1.0"`.
- [ ] `uv run dbt-column-lineage --help` exits 0 and shows the Typer help text.
- [ ] `uv run pytest` passes (at least `test_smoke`).
- [ ] `ruff check` and `ruff format --check` are clean.
- [ ] CI workflow file present and internally consistent with the commands above.
- [ ] `src/dbt_column_lineage/CLAUDE.md` exists.
