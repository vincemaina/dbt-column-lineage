# START HERE — Implementer entry point

You are implementing **Phase 1** of the dbt column-lineage engine. This file is your launch point.
Follow it exactly. Do not rely on any external conversation — everything you need is in these files.

## Your loop

1. **Read the protocol once:** [`README.md`](./README.md) (how to work a task, the global *Definition of
   done*, conventions, and when to escalate). Then read [`../architecture.md`](../architecture.md) §1–§4
   for the shape of what you're building.
2. **Find your current task:** open [`CHECKLIST.md`](./CHECKLIST.md) and pick the **lowest-numbered task
   whose box is unchecked (☐)**. That is your task. (This is how you know where to start *and* where to
   resume — progress lives in the checklist, not in memory.)
3. **Do that task** per its `task-NN-*.md` file and the *Definition of done*. Implement only that task.
4. **Verify** — run every command in the task's *Verify* section; all must pass.
5. **Check it off** — tick the box in `CHECKLIST.md`, add any handoff note the next task needs.
6. **Decide whether to continue or stop** (see below).

## When to STOP and ask for review

Stop, do **not** start the next task, and post a short summary (see *Handoff format*) when **any** of
these is true:

- ✋ **You just finished a task whose "Review gate" column is `yes`** in `CHECKLIST.md`
  (tasks 02, 03, 06, 07, 11). Opus must review before the next task begins.
- ✋ **You hit an escalation** — a requirement is ambiguous, contradicts the architecture, needs a new
  dependency, or you can't make tests pass without changing a specified interface. Write the question
  under `## Open questions for Opus` at the bottom of the current task file, then stop.
- ✋ **A verify step fails and you cannot fix it within the task's stated scope.**

If none of these apply, continue automatically to the next task (step 2).

## When you reach the end

When every box in `CHECKLIST.md` is ticked, stop and report that Phase 1 is complete and ready for final
review.

## Handoff format (what to print when you stop)

```
STOPPED at task NN — <reason: review gate | escalation | blocked>
Done since last stop: <task numbers>
What changed: <one line per task — files added/changed>
Verify status: <commands run + pass/fail>
Needs from Opus: <review of task NN | answer to open question | unblock>
```

## Hard rules (repeat of the important ones)

- **One task at a time, in order.** Never skip ahead or batch tasks past a review gate.
- **Never run git** (no commit/branch/push) — that's the user's job. Leave the tree ready for review.
- **Never add a dependency** beyond `sqlglot[rs]`, `typer`, `pytest`, `ruff` without asking.
- **Match the architecture's names/IR exactly.** When unsure, ask — a wrong interface ripples forward.
- **No silent guessing** — in code, unresolved lineage/schema must produce the specified warning +
  `unknown` provenance, never a fabricated edge.
