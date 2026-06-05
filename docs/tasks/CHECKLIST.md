# Phase 1 Checklist

New here? Start at [`START_HERE.md`](./START_HERE.md).

Work top to bottom. Tick a box only when the task's *Definition of done* (see
[`README.md`](./README.md)) is fully satisfied. The **current task is the lowest unchecked box.**
**Review gate** tasks must be reviewed by Opus before the next task starts.

| # | Task | Review gate | Status |
|---|------|:-----------:|:------:|
| 01 | [Package scaffold & tooling](./task-01-scaffold.md) | no | ☐ |
| 02 | [Lineage IR data model](./task-02-ir.md) | **yes** | ☐ |
| 03 | [Synthetic test fixture + oracle](./task-03-fixture.md) | **yes** | ☐ |
| 04 | [Artifact loaders (manifest/catalog)](./task-04-loaders.md) | no | ☐ |
| 05 | [Catalog schema resolver](./task-05-catalog-resolver.md) | no | ☐ |
| 06 | [SQLGlot lineage adapter](./task-06-sqlglot-adapter.md) | **yes** | ☐ |
| 07 | [Transform classifier + edge builder](./task-07-transform-classifier.md) | **yes** | ☐ |
| 08 | [Lineage graph + transitive traversal](./task-08-graph.md) | no | ☐ |
| 09 | [Serializers (JSON + Mermaid)](./task-09-serializers.md) | no | ☐ |
| 10 | [dbt node selector](./task-10-selector.md) | no | ☐ |
| 11 | [CLI + end-to-end tests](./task-11-cli.md) | **yes** | ☐ |

**Notes / handoffs** (Implementer fills in as tasks complete — e.g. resolved sqlglot version, deviations
approved by Opus, anything the next task should know):

- _(none yet)_

---
_All 11 task files are written. Begin at [`START_HERE.md`](./START_HERE.md)._
