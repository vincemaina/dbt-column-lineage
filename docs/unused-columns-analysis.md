# Unused Columns Analysis Feature

## Overview

A new analysis layer that identifies columns created in dbt models but not actually used downstream — either never referenced, or only feeding other columns that themselves have no use. This helps identify "dead weight" columns that can be safely removed, while allowing whitelisting of metadata-only columns.

## Core Capability

The analysis answers: **"Which columns exist in this project but don't contribute to anything useful?"**

Useful contributions include:
- Feeding into output columns of downstream models
- Being exposed via dbt exposures (BI tools, dashboards, etc.)
- Being relied upon by tests (flagged separately for review)
- Being whitelisted (metadata columns: audit trails, timestamps, etc.)

## Design Decisions (For Your Review)

These capture the judgment calls needed to make the tool practical:

### 1. **Test-Only Columns**
**Decision:** Flag separately as `TEST_ONLY` reason, not automatically removed.

**Rationale:** A column might not feed downstream models but still be valuable if it has a rigorous test. Example: a checksum column that validates data integrity. The test is useful even if the column isn't surfaced.

**Output:** Separate finding with suggested action "review" rather than "remove".

**Impact on dbt-test-lineage:** The test-lineage tool will see this column has zero guaranteed coverage — this is additional signal (why test an unused column? Maybe it's valuable, or maybe the test should move).

---

### 2. **Control-Only Columns**
**Decision:** Flag as separate reason `CONTROL_ONLY`, not `DEAD`.

**Rationale:** A column used only in join conditions or filter predicates (value not propagated downstream) is still useful—it's part of the model's logic. A model with no join keys is often buggy.

**Example:** A join key that matches two tables but doesn't appear in the output.

**Output:** Flag for review (not automatic removal).

---

### 3. **Ephemeral Models**
**Decision:** Treat ephemeral columns same as table/view columns.

**Rationale:** Materialization doesn't matter. We care whether the column contributes to anything useful downstream, whether it's ephemeral, table, or view.

**Impact:** Ephemeral models can have unused columns too (they just don't accumulate in the warehouse).

---

### 4. **Incremental Models & {{ this }}**
**Decision:** Treat `{{ this }}` self-references as **not contributing to downstream lineage** (they're structural scaffolding, not value lineage).

**Rationale:** 
- In `DELETE + INSERT` incremental models, the old rows are deleted entirely—the `{{ this }}` self-reference doesn't flow into the next run's output.
- In `MERGE` models, the match condition feeds the merge logic, not the output value.
- Self-references are captured separately in `LineageResult.self_references` for potential future use, but they don't count as "downstream usage" for dead-column purposes.

**Output:** Columns that only self-reference will be flagged as `NEVER_USED`.

---

### 5. **Exposures**
**Decision:** Include columns referenced in dbt `exposures` as "used downstream."

**Rationale:** If Looker (or another BI tool) explicitly references a column via a dbt exposure, that's real downstream usage.

**Implementation:**
- Parse `manifest.exposures[*].depends_on.nodes` to find exposed models.
- For each exposed model, check if it has `columns` metadata (column-level exposure definitions).
- If no column-level detail, assume all columns are potentially exposed (conservative).
- If column-level detail exists, only those columns are exposed.

**Caveat:** dbt exposures are optional and often incomplete. A missing exposure doesn't mean a column is unused—it might just not be declared.

---

### 6. **Confidence Levels**
**Decision:** Three-tier confidence system:

| Confidence | Scenario |
|---|---|
| **HIGH** | No lineage found at all (column truly never used) |
| **MEDIUM** | Lineage exists but all downstream paths lead to unused columns (transitive dead weight); or column is control-only; or only used by tests |
| **LOW** | Lineage exists, downstream usage is uncertain due to low-confidence upstream lineage (UNKNOWN transforms, schema provenance); or lineage depends on exposures being complete |

**Output:** Each unused column includes confidence; users should review LOW-confidence findings.

---

### 7. **Dead Chain Detection**
**Decision:** Recursively flag columns that feed only dead columns.

**Rationale:** A column that generates only other unused columns is transitively dead—removing it should be safe.

**Implementation:**
- Build a reverse dependency graph: for each column, what does it feed?
- Mark leaf columns (zero outgoing edges to used columns) as unused.
- Recursively mark columns that feed only unused columns.
- Track the chain for transparency: `"dead_chain_reason": "feeds only [col_x (NEVER_USED), col_y (NEVER_USED)]"`.

---

### 8. **Seed & Source Columns**
**Decision:** Flag unused columns in seeds and sources (not just models).

**Rationale:** Seeds are often used as lookup tables—an unused column in a seed is also dead weight.

**Output:** Same report, applies to all asset types.

---

## Output Format

Aligns with existing engine outputs: JSON-based with optional text summaries.

### JSON Report Structure

```json
{
  "metadata": {
    "generated_at": "2026-06-08T10:30:00Z",
    "whitelist_applied": {
      "patterns": ["_inserted_at", "_incremented_at"],
      "count_excluded": 42
    },
    "schema_mode": "catalog",
    "dialect": "snowflake"
  },
  "unused_columns": [
    {
      "asset": "model.my_project.my_model",
      "column": "unused_field",
      "reason": "NEVER_USED",
      "confidence": "high",
      "feeds": {
        "columns": [],
        "tests": []
      },
      "used_in_control": false,
      "matches_whitelist_pattern": null,
      "suggestion": "remove"
    },
    {
      "asset": "model.my_project.my_model",
      "column": "join_key",
      "reason": "CONTROL_ONLY",
      "confidence": "high",
      "feeds": {
        "columns": [],
        "tests": []
      },
      "used_in_control": true,
      "control_usage": ["JOIN"],
      "matches_whitelist_pattern": null,
      "suggestion": "review"
    },
    {
      "asset": "model.my_project.my_model",
      "column": "test_field",
      "reason": "TEST_ONLY",
      "confidence": "medium",
      "feeds": {
        "columns": [],
        "tests": ["test.my_project.my_model_test_field_not_null_abc123"]
      },
      "used_in_control": false,
      "matches_whitelist_pattern": null,
      "suggestion": "review"
    },
    {
      "asset": "model.my_project.upstream_model",
      "column": "intermediate_calc",
      "reason": "DEAD_CHAIN",
      "confidence": "medium",
      "feeds": {
        "columns": ["model.my_project.my_model.unused_field"],
        "tests": []
      },
      "dead_chain_reason": "feeds only [unused_field (NEVER_USED)]",
      "used_in_control": false,
      "matches_whitelist_pattern": null,
      "suggestion": "review"
    },
    {
      "asset": "model.my_project.my_model",
      "column": "created_at",
      "reason": "WHITELISTED",
      "confidence": "high",
      "feeds": {
        "columns": [],
        "tests": []
      },
      "used_in_control": false,
      "matches_whitelist_pattern": "_at$",
      "suggestion": "keep"
    }
  ],
  "summary": {
    "total_assets": 250,
    "assets_with_unused": 45,
    "total_columns": 12345,
    "unused_count": 234,
    "whitelisted_count": 42,
    "unused_by_reason": {
      "NEVER_USED": 150,
      "TEST_ONLY": 30,
      "DEAD_CHAIN": 34,
      "CONTROL_ONLY": 20
    },
    "unused_by_confidence": {
      "HIGH": 180,
      "MEDIUM": 54,
      "LOW": 0
    }
  }
}
```

### Text Summary (CLI Output)

```
Unused Columns Report
=====================

Total columns: 12,345
Unused: 234 (1.9%)
Whitelisted: 42

By Reason:
  NEVER_USED    150  (64.1%)
  TEST_ONLY      30  (12.8%)
  DEAD_CHAIN     34  (14.5%)
  CONTROL_ONLY   20   (8.6%)

By Confidence:
  HIGH           180 (77.0%)
  MEDIUM          54 (23.0%)
  LOW              0 ( 0.0%)

Top findings by asset (remove priority):
  model.my_project.my_model            : 12 unused (10 HIGH, 2 MEDIUM)
  model.my_project.other_model         :  8 unused (8 HIGH)
  ...

Use --json for detailed column-by-column breakdown.
```

---

## Whitelist Configuration

**Format:** JSON file (user-maintained, external to code).

**File:** `.dbt-column-lineage-unused-whitelist.json` (or custom path via `--whitelist`).

```json
{
  "comment": "Columns that exist for operational/metadata reasons and should not be flagged as unused",
  "column_patterns": [
    "_inserted_at",
    "_incremented_at",
    "_loaded_at",
    "dbt_updated_at",
    "_scd_start_dts",
    "_scd_end_dts"
  ],
  "specific_columns": [
    "model.my_project.my_audit_table.internal_flag",
    "source.my_project.raw.raw_events.raw_json"
  ],
  "assets_to_ignore": [
    "model.my_project.debug_staging",
    "model.my_project.test_sandbox_*"
  ]
}
```

**Matching:**
- `column_patterns`: regex (anchored, e.g., `_at$` matches `created_at`, `updated_at` but not `atlas`).
- `specific_columns`: exact match on `asset.column`.
- `assets_to_ignore`: glob patterns (e.g., `test_sandbox_*` matches all columns in models starting with `test_sandbox_`).

**CLI Usage:**
```bash
dbt-column-lineage unused --manifest ... --catalog ... --whitelist .dbt-column-lineage-unused-whitelist.json
```

---

## Caching Strategy

**Goal:** Re-analyzing should be fast; only re-extract/re-analyze when inputs change.

**Approach:** 
- Cache the `LineageResult` (already done in dbt-test-lineage via `extract_lineage_cached`).
- Use same caching mechanism here.
- For unused-columns analysis specifically, add a separate cache keyed on:
  - `LineageResult` hash (upstream cache key)
  - Whitelist file hash (if provided)
  - Any dbt manifest changes affecting exposures/tests
  - Analysis parameters (e.g., schema_mode)

**Implementation:**
```python
def analyze_unused_cached(
    lineage_result: LineageResult,
    manifest: dict,
    whitelist_path: Path | None = None,
    cache_dir: Path | None = None
) -> tuple[UnusedColumnsReport, bool]:
    """
    Analyze unused columns with caching.
    
    Returns: (report, from_cache)
    """
    # Compute cache key
    key = _cache_key(lineage_result, manifest, whitelist_path)
    
    if cache_dir and (cache_path := cache_dir / f"{key}.json").exists():
        return UnusedColumnsReport.load(cache_path), True
    
    # Compute
    report = analyze_unused(lineage_result, manifest, whitelist_path)
    
    # Store
    if cache_dir:
        cache_path.write_text(report.to_json())
    
    return report, False
```

---

## CLI Integration

**New command:**
```bash
dbt-column-lineage unused [OPTIONS]
```

**Options:**
```
  --manifest PATH                   Path to manifest.json (required)
  --catalog PATH                    Path to catalog.json (optional, for schema mode)
  --schema-mode {auto|catalog|inferred|hybrid}
                                    Schema resolution mode (default: auto)
  --whitelist PATH                  Path to whitelist JSON (optional)
  --format {json|text}              Output format (default: text)
  --output PATH                     Write report to file (optional; default: stdout)
  --confidence {all|high|medium}    Filter by confidence (default: all)
  --reason {all|NEVER_USED|...}     Filter by reason (default: all)
  --cache PATH                      Cache directory (optional)
  --show-cache-hit                  Print cache hit status to stderr
```

**Example:**
```bash
dbt-column-lineage unused \
  --manifest target/manifest.json \
  --catalog target/catalog.json \
  --whitelist .dbt-column-lineage-unused-whitelist.json \
  --format json \
  --output unused-columns.json
```

---

## Implementation Plan

### Phase A: Core Analysis (No caching yet)

**New module:** `unused_columns.py`
- `UnusedColumnsReport` dataclass (immutable, JSON-serializable)
- `UnusedColumn` dataclass (one row in the report)
- `analyze_unused(lineage_result, manifest, whitelist) -> UnusedColumnsReport`
- Helper functions:
  - `_parse_whitelist(path) -> Whitelist`
  - `_is_whitelisted(asset, column, whitelist) -> bool`
  - `_find_test_users(column_ref, manifest) -> list[str]`
  - `_find_exposure_users(column_ref, manifest) -> bool`
  - `_find_dead_chains(lineage_result, manifest) -> dict[ColumnRef, list[ColumnRef]]`

**Update:** `cli.py` add `unused` command.

**Tests:** `tests/test_unused_columns.py` — unit + integration tests for:
- Dead chain detection
- Test-only columns
- Control-only columns
- Exposure detection
- Whitelist matching (exact, regex, glob)
- Confidence assignment

### Phase B: Caching (Optional, can add after Phase A)

- Add `_cache_key()` and `analyze_unused_cached()` helper.
- Wire into CLI.

### Phase C: Documentation

- Add to `docs/architecture.md` as a Phase 5 feature.
- Add to `ROADMAP.md`.
- Update `CLAUDE.md` in `src/` to document the new module.

---

## Known Unknowns & Edge Cases (For Future Refinement)

1. **Exposures with missing column-level detail:** Conservative assumption (all columns exposed). Consider flag to be stricter.

2. **Dynamic column generation:** Columns generated via `*` or dbt macros might not be visible in the manifest. Could cause false positives.

3. **Non-dbt downstream:** Columns used outside dbt (e.g., direct SQL queries, BI tool direct queries). Exposures help, but are incomplete.

4. **Materialized views / snapshots:** Should they be analyzed? Current plan: yes, treat like normal models.

---

## Questions for You

1. **Whitelist location:** Should default location be `.dbt-column-lineage-unused-whitelist.json` in the project root? Or always require explicit `--whitelist` flag?

2. **Suggestion field:** Should it be `remove | review | keep`, or more granular (e.g., `remove | review_test | review_control | keep | investigate`)?

3. **Filtering:** Should the CLI support `--reason NEVER_USED,TEST_ONLY` to show only certain types?

4. **Output:** Should text format show individual findings, or just the summary? (Full JSON always available via `--json`.)

5. **Real-repo test:** Once designed, would you like me to run this on your actual dbt repo to show example output before we finalize implementation?

---

## Success Criteria

- [ ] Correctly identifies columns with zero downstream usage in fixture
- [ ] Flags test-only columns separately
- [ ] Detects dead chains (columns feeding only dead columns)
- [ ] Whitelist matching works for patterns, specific columns, and asset globs
- [ ] Confidence system is intuitive and documented
- [ ] JSON output is deterministic and matches the schema above
- [ ] CLI integrates cleanly into existing tool
- [ ] Real-repo test shows sensible findings (reviewed manually)
- [ ] All decisions documented so user can review & adjust

