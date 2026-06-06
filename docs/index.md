# dbt-column-lineage

A local, static **column-level lineage engine for dbt projects** (Snowflake-first), built on
[SQLGlot](https://github.com/tobymao/sqlglot). It consumes dbt artifacts (`manifest.json` +
`catalog.json`) and produces a rich, machine-readable lineage IR — value lineage with full **transform
chains**, control/INDIRECT lineage, model-level operation facts, and self-references — recording **facts,
not verdicts**.

## How to read these docs

- **[Architecture](architecture.md)** — the source of truth: locked decisions, pipeline stages, the
  lineage IR, schema-resolution strategy, outputs, non-goals.
- **[Use cases](use-cases.md)** — what consumes the IR (test assurance, impact analysis, PII
  propagation, breaking-change detection) and the engine facts each leans on.
- **[API reference](reference/)** — auto-generated per-module, drilling down to every public class and
  function with its signature, docstring, and source. Start at the high-level modules and click in:
    - `engine` — the public entrypoint (`extract_lineage`)
    - `sql_adapter` / `classify` — SQLGlot-facing extraction + the transform-chain builder
    - `control` — control lineage + model operation facts
    - `ir` — the lineage IR contract
    - `inference` / `hybrid` / `schema_resolver` — schema resolution (catalog / inferred / hybrid)

## Pipeline at a glance

```
manifest.json + catalog.json
        │  artifacts.py        (load typed DbtArtifacts)
        ▼
   schema resolution           (schema_resolver / inference / hybrid)
        │
        ▼
   sql_adapter.py              (SQLGlot lineage per model)
        │
        ▼
   classify.py                 (transform chains + LineageEdges)  + control.py (controls, operations)
        │
        ▼
   engine.py  →  LineageResult →  serialize.py (JSON / Mermaid) · graph.py (traversal) · cli.py
```
