# docs/tasks/

Self-contained, checkable work orders that break [Phase 1](../phase-1-mvp.md) into 11 ordered tasks for
an implementer agent. Designed to be executed with **no external chat context**.

## Entry point

- [`START_HERE.md`](./START_HERE.md) — **point the implementer agent at this file.** It tells the agent
  to read the protocol, find the current task from the checklist, work it, and stop at review gates.

## Process files

- [`README.md`](./README.md) — working protocol: how to do a task, the global *Definition of done*,
  conventions (package layout, `uv`, deps, no-git), and escalation rules.
- [`CHECKLIST.md`](./CHECKLIST.md) — the ordered, checkable task list. **Progress lives here** — the
  current task is the lowest unchecked box. Marks which tasks are Opus review gates.

## Task files

`task-01` … `task-11`, executed in order. Each has: Objective, Context, Prerequisites, Files to create,
Requirements, Verify commands, and Acceptance criteria. Review-gate tasks (02, 03, 06, 07, 11) end with
an `Open questions for Opus` section and must be reviewed before the next task starts.

All eleven task files (`task-01`–`task-11`) are written and ready to execute.
