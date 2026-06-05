# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

This project is **pre-implementation**. There is no source code yet. The repository
currently contains only:

- `pyproject.toml` — package metadata (`dbt-column-lineage`, Python `>=3.12`, no dependencies declared yet).
- `notes/chatgpt/` — research and design context copied from a ChatGPT conversation. These are
  **starting context, not finalized decisions**. Per `notes/chatgpt/CLAUDE.md`, final design decisions
  are to be discussed and agreed with the user before implementing.
- `.venv/` — local virtual environment (Python 3.12+).

There is no build, lint, or test tooling configured yet. When adding it, prefer `uv` or standard
`pip`/`venv` against the existing `.venv`, and wire commands into `pyproject.toml`.

`notes/chatgpt/PROMPT.md` and `notes/chatgpt/chatgpt-other-thoughts.md` contain the full design brief
and an existing-tools landscape survey. Read them before doing substantive work.

## What this project is

A general-purpose, **open-source column-lineage engine for dbt projects**. It parses dbt artifacts and
SQL to determine column-to-column relationships, and exposes them as a neutral, machine-readable graph.

Critical scoping rule: this is the **first of two separate projects**. A later test-lineage / assurance
tool will *consume* this engine's output, but **no test-lineage-specific reasoning belongs in this
package**. Keep this engine general-purpose so it can also serve impact analysis, metadata/PII
propagation, PR review tooling, and visualization.

## Design constraints (from the brief)

These shape implementation decisions and should be treated as load-bearing:

- **Schema-aware** parsing is a core requirement — without schema info, `select *` and unqualified
  columns across joins cannot be resolved reliably.
- **Conservative and explainable**: never silently guess lineage. Represent ambiguity, confidence,
  parsing failures, and unsupported constructs explicitly. Expose partial results alongside warnings.
- **Richer than column pairs**: the lineage representation should distinguish, at minimum,
  - **value lineage** (columns whose values contribute to an output value) vs.
    **control/influence lineage** (columns used in filters, joins, grouping, ordering, window partitioning);
  - transformation categories (passthrough, rename, cast, deterministic expression, aggregation,
    window, case, coalesce, union, join-derived, unknown);
  - direct vs. transitive lineage.
- **Deterministic, repo-agnostic, locally runnable** (no required hosted service); usable both as a
  **Python library** and a **standalone CLI** suitable for CI.
- **Modular boundaries** to keep parsers/artifact versions swappable. The intended pipeline stages are:
  dbt artifact loading → schema resolution → SQL parsing → lineage extraction → graph traversal →
  serialization/export → CLI presentation → optional visualization adapters.

The working hypothesis in the brief is to build a thin dbt-specific layer around **SQLGlot** (its
lineage API), treating Canva's `dbt-column-lineage-extractor` as the closest reference implementation.
Inputs are expected to be dbt `manifest.json` / `catalog.json` / compiled SQL, with Snowflake as the
priority dialect. Do not commit to these choices in code without confirming with the user.

## Working practices

These are the user's standing conventions for how to work in this repo. The full rationale lives in
`claude-best-practices.md`; the load-bearing rules are summarized here.

- **Git is the user's job. Do not run git commands** — no commits, pushes, branches, tags, rebases,
  merges, or stashes on your own initiative. Suggest commit messages or describe the diff when useful,
  but let the user execute. If explicitly told to perform a git action, treat it as a **one-time
  exception** for that task only — do not adopt it as a new default; wait for the user again next time.
- **CLAUDE.md in every subfolder.** Each subfolder should have its own `CLAUDE.md` describing every file
  and subfolder it contains. The intent is to add a test that enforces both presence and that the
  summary references all files in the folder. Keep these small and current.
- **Plan before building.** For non-trivial work, produce a plan first (web research included where
  relevant). Plans are worth committing to git as a decision log; couple them with roadmaps — the
  roadmap turns a plan's brief into actionable, referenced steps.
- **Roadmaps as the starting point.** Prefer a top-level `ROADMAP.md` that summarizes direction and
  links to per-phase / per-feature roadmap files, rather than one monolithic file.
- **Research before substantial work.** Doing web research up front (on tools, APIs, SQL/dbt semantics)
  measurably improves results — do it before committing to an approach.
- **Build skills as you learn.** When you work out how to use an external tool/API/package, capture it
  as a Claude skill so it is reusable (research → write skill → it becomes available next session).
- **Tests guard both code and practices.** Maintain a fast test suite to catch regressions, and also use
  tests to enforce working conventions (e.g. the per-folder `CLAUDE.md` rule above).
- **Prefer end-to-end self-verification.** Where possible, give yourself a way to exercise the real
  output (CLI runs against fixture dbt projects, not just unit tests) and verify work before reporting
  it done.

Because this repo is at the design stage, also prefer discussing and confirming architectural decisions
with the user before writing significant code, as requested in `notes/chatgpt/CLAUDE.md`.
