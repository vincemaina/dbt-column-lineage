# tests/fixtures/

Test fixtures for the lineage engine.

## Contents

- [`jaffle/`](./jaffle/) — the primary synthetic dbt project artifacts + the hand-authored,
  sqlglot-verified lineage **oracle** (`expected_lineage.json`). This is the reproducible correctness
  reference the engine is tested against. See [`jaffle/README.md`](./jaffle/README.md).

Real-world validation (the user's actual dbt repo) is done manually against a clone in the gitignored
`local/` folder — never committed here.
