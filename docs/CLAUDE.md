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
- [`index.md`](./index.md) — landing page for the rendered docs **site** (mkdocs).

## Docs site (mkdocs-material + mkdocstrings)

`mkdocs.yml` (repo root) + `scripts/gen_ref_pages.py` build a navigable, searchable site: Home →
Architecture → Use cases → **auto-generated per-module API reference** (every public class/function with
signature, docstring, and expandable source — the "start high, click down" view). Run it:

```
uv sync --group docs
uv run mkdocs serve     # live preview at http://127.0.0.1:8000
uv run mkdocs build     # static site -> ./site/ (gitignored)
```

`CLAUDE.md` and `tasks/` are excluded from the site (dev-internal). The API pages are generated, not
hand-written, so they never drift from the code.

## Subfolders

- [`tasks/`](./tasks/) — Phase 1 broken into 11 self-contained, checkable work orders for an implementer
  agent. The entry point is [`tasks/START_HERE.md`](./tasks/START_HERE.md); progress is tracked in
  [`tasks/CHECKLIST.md`](./tasks/CHECKLIST.md).

## Related (outside this folder)

- [`../ROADMAP.md`](../ROADMAP.md) — high-level phased roadmap linking to per-phase plans.
- [`../notes/chatgpt/`](../notes/chatgpt/) — original research brief and landscape survey (starting
  context, superseded by `architecture.md` where they disagree).
