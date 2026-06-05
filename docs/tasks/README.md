# Phase 1 Tasks — Working Protocol

This folder breaks [Phase 1](../phase-1-mvp.md) into small, self-contained, checkable work orders.
Each `task-NN-*.md` is designed to be completed **without needing any prior chat context** — read the
task file and the files it links, do exactly that task, verify, check it off.

If anything below is ambiguous, **stop and ask** (see *Escalation*). Do not guess on architecture.

## Roles

- **Implementer (Haiku):** executes one task at a time, in order, following the spec exactly.
- **Reviewer (Opus):** sets direction, answers escalations, and reviews tasks marked **Review gate: yes**
  before dependent tasks may start.

## How to work a task

1. Open the lowest-numbered unchecked task in [`CHECKLIST.md`](./CHECKLIST.md).
2. Read the **whole** task file, plus every file it links under *Context* and *Prerequisites*.
3. Implement **only** what that task specifies. Do not start later tasks' work.
4. Run every command under *Verify*. All must pass.
5. Confirm every box under *Acceptance criteria* is genuinely true.
6. Update [`CHECKLIST.md`](./CHECKLIST.md): tick the task, fill in the "done" notes if asked.
7. If the task created a new source folder, add a `CLAUDE.md` to it (see *Conventions*).
8. **Stop.** If the task is a *Review gate*, do not start the next task — wait for Opus review.

## Definition of done (applies to every task)

A task is done only when ALL of these hold:

- [ ] The specified files exist with the specified behaviour.
- [ ] Type hints on all public functions/classes; clear, minimal code matching surrounding style.
- [ ] Unit tests written for this task's code and **passing**: `uv run pytest`.
- [ ] Lint clean: `uv run ruff check .` and `uv run ruff format --check .`.
- [ ] Every *Acceptance criteria* box is satisfied.
- [ ] The IR / interfaces match [`../architecture.md`](../architecture.md) exactly — no ad-hoc renames.
- [ ] `CHECKLIST.md` updated; new source folders have a `CLAUDE.md`.

## Conventions

- **Package:** source lives in `src/dbt_column_lineage/`, imported as `dbt_column_lineage`.
  Tests live in `tests/`. (`src/` layout — set up in task 01.)
- **Run things with `uv`:** `uv run pytest`, `uv run ruff check .`, `uv run dbt-column-lineage …`.
- **Dependencies:** only the agreed stack (`sqlglot[rs]`, `typer`; dev: `pytest`, `ruff`). **Do not add
  any other dependency without asking Opus first.**
- **Names match the architecture doc.** Enum values, field names, and module names come from
  [`../architecture.md`](../architecture.md) §4. If it's not specified there or in the task, ask.
- **No silent guessing in the code itself either** — when lineage/schema can't be resolved, emit the
  specified warning + `unknown` provenance; never fabricate an edge.
- **Per-folder `CLAUDE.md`:** any new folder under `src/` or `tests/` gets a short `CLAUDE.md` listing
  its files and their purpose (project convention — see [`../../claude-best-practices.md`](../../claude-best-practices.md)).
- **Git is the user's job.** Do **not** run any git commands (no commit/branch/push). Just leave the
  working tree ready for review.

## Escalation (when to stop and ask Opus)

Stop and write your question under a `## Open questions for Opus` heading **at the bottom of the task
file**, then halt, if:

- A requirement is ambiguous or seems to contradict the architecture doc.
- You need a decision the task doesn't cover (a new dependency, an interface change, an edge case the
  spec is silent on).
- A *Review gate* task is complete and needs sign-off.
- Tests can't be made to pass without changing the specified interface.

Better to ask than to guess — a wrong interface ripples into every later task.
