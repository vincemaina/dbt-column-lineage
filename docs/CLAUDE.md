# docs/

Design documentation and decision log for the dbt column-lineage engine. Keep these current as
decisions evolve — they are the source of truth, ahead of the (not-yet-existing) code.

## Files

- [`architecture.md`](./architecture.md) — architectural source of truth and decision log: what the
  tool is, the locked decisions, pipeline stages, the lineage IR, schema-resolution strategy, outputs,
  CLI surface, non-goals, stack, and risks. **Read this first.**
- [`phase-1-mvp.md`](./phase-1-mvp.md) — detailed plan for the first milestone (catalog-authoritative
  MVP): scope, test strategy, acceptance criteria, build order.
- [`use-cases.md`](./use-cases.md) — directional map of what consumes the lineage IR (assurance, impact
  analysis, PII propagation, breaking-change detection, …) and the engine facts each leans on; keeps the
  IR neutral and rich enough to serve more than one consumer.

## Subfolders

- [`tasks/`](./tasks/) — Phase 1 broken into 11 self-contained, checkable work orders for an implementer
  agent. The entry point is [`tasks/START_HERE.md`](./tasks/START_HERE.md); progress is tracked in
  [`tasks/CHECKLIST.md`](./tasks/CHECKLIST.md).

## Related (outside this folder)

- [`../ROADMAP.md`](../ROADMAP.md) — high-level phased roadmap linking to per-phase plans.
- [`../notes/chatgpt/`](../notes/chatgpt/) — original research brief and landscape survey (starting
  context, superseded by `architecture.md` where they disagree).
