I want to investigate and potentially build an open-source, general-purpose column-lineage tool for dbt projects.

## Wider context

This is the first of two separate projects.

The eventual second project will be a dbt test-lineage or assurance-analysis tool. That tool will trace properties such as `not_null`, `unique`, and `accepted_values` through a dbt model lineage and identify:

* gaps where an upstream guarantee may have been invalidated but no downstream test re-establishes it;
* tests that may be redundant because an upstream guarantee has been preserved;
* transformations where it is uncertain whether a guarantee remains valid.

To support that future tool, we first need a reliable column-lineage engine.

However, the column-lineage project must remain independent and general-purpose. It should not contain test-lineage-specific reasoning. It may later be used for:

* impact analysis;
* documentation and metadata propagation;
* PII or classification propagation;
* PR review tooling;
* model-refactoring assistance;
* visualising lineage;
* other downstream static-analysis tools.

The test-lineage tool should eventually consume the column-lineage project as a Python package, CLI dependency, or structured-data provider.

## Immediate task

Do not begin implementing the tool yet.

First, conduct a detailed investigation of the current column-lineage landscape and recommend whether we should:

1. use an existing tool directly;
2. build a wrapper or extension around an existing tool;
3. fork an existing open-source project;
4. combine components from multiple projects;
5. build a new dbt-specific lineage layer on top of a lower-level SQL parser.

Prioritise open-source tools and reusable libraries, but also inspect commercial or platform-native offerings to understand their capabilities and limitations.

## Existing offerings to investigate

At minimum, investigate:

* SQLGlot and its lineage API;
* Canva's `dbt-column-lineage-extractor`;
* SQLLineage;
* LineageX and dbt-LineageX;
* OpenLineage and its column-lineage facet;
* DataHub's SQL parser and column-level lineage;
* OpenMetadata's dbt and column-lineage support;
* dbt Catalog, dbt Docs v2, and dbt Fusion column-level lineage.

Search for any other actively maintained or technically relevant projects.

For each offering, determine:

* whether it extracts lineage or only stores/displays lineage produced elsewhere;
* whether it is dbt-specific or general SQL;
* whether it operates statically or requires runtime/query-history metadata;
* supported SQL dialects, especially Snowflake;
* whether it consumes dbt `manifest.json`, `catalog.json`, compiled SQL, or warehouse schemas;
* whether it is schema-aware;
* treatment of `select *`;
* treatment of unqualified or ambiguous columns;
* handling of CTEs, subqueries, ephemeral models, snapshots, seeds, sources, incremental models, unions, joins, window functions, lateral joins, JSON extraction, macros, and Python models;
* whether it distinguishes passthrough, rename, and transformation;
* whether it records the transformation expression;
* whether it records columns used in joins, filters, grouping, ordering, and window definitions;
* whether it distinguishes direct lineage from transitive lineage;
* whether it reports confidence, ambiguity, parsing failures, or unsupported constructs;
* available Python APIs, CLI interfaces, and output formats;
* licensing;
* maintenance activity;
* extensibility;
* test coverage and apparent production readiness.

Do not rely only on README claims. Inspect source code, tests, open issues, recent commits, and architecture where useful.

## Important distinction

Clearly separate these three concerns:

1. **Lineage extraction**

   * Parsing SQL and dbt metadata to determine column relationships.

2. **Lineage interchange and storage**

   * Standards and schemas such as OpenLineage.

3. **Lineage presentation**

   * CLI output, JSON, Mermaid, interactive graphs, and metadata-platform UIs.

A large metadata platform may provide excellent storage and visualisation without being appropriate as the extraction engine for a lightweight reusable package.

## Required capabilities for our likely tool

The lineage engine should ideally be usable both:

* as a Python library by other tools;
* as a standalone CLI by engineers and CI workflows.

A possible CLI experience could eventually resemble:

```bash
dbt-column-lineage extract \
  --manifest target/manifest.json \
  --catalog target/catalog.json \
  --dialect snowflake \
  --select model_name+ \
  --output lineage.json
```

Possible additional commands could include:

```bash
dbt-column-lineage upstream model.column
dbt-column-lineage downstream model.column
dbt-column-lineage explain model.column
dbt-column-lineage validate
dbt-column-lineage graph model.column --format mermaid
```

Do not treat these exact commands as final requirements. Evaluate what interface would be most useful.

## Desired internal representation

Investigate and propose a neutral intermediate representation for lineage.

The representation should not be coupled to a particular UI or to the future test-lineage project.

At minimum, consider whether each lineage edge should contain:

* upstream asset and column;
* downstream asset and column;
* relationship type;
* transformation category;
* relevant SQL expression;
* source model or query;
* direct versus transitive status;
* confidence level;
* ambiguity or warning information;
* SQL dialect;
* columns used by the transformation but not directly projected;
* source-code location where available.

For example, distinguish between:

* direct passthrough;
* rename;
* cast;
* deterministic expression;
* aggregation;
* window function;
* case expression;
* coalesce;
* union;
* join-derived output;
* unknown transformation.

Also consider whether the graph should distinguish:

* **value lineage**: columns whose values contribute to the output value;
* **control or influence lineage**: columns used in filters, joins, grouping, ordering, or window partitioning that affect which output values exist.

The future test-lineage tool may require richer information than a basic `upstream_column -> downstream_column` graph, but those future semantics must remain outside the column-lineage package itself.

## Architectural principles

The project should be:

* repo-agnostic;
* configurable rather than company-specific;
* usable locally without requiring a hosted service;
* deterministic and explainable;
* conservative when lineage is uncertain;
* able to expose partial results alongside warnings;
* modular enough to support different SQL parsers or dbt artifact versions;
* suitable for eventual use in CI and a possible GitHub App;
* designed around a stable public Python API and machine-readable output.

Avoid silently guessing lineage. Prefer explicit ambiguity and confidence metadata.

Consider whether the architecture should separate:

* dbt artifact loading;
* schema resolution;
* SQL parsing;
* lineage extraction;
* graph traversal;
* serialisation/export;
* CLI presentation;
* optional visualisation adapters.

## Key questions to answer

1. What is the closest existing solution to what we need?
2. Does any existing tool already provide a sufficiently rich and stable API?
3. Is SQLGlot the correct underlying parser, or are there stronger alternatives?
4. Should Canva's dbt column-lineage extractor be used, extended, forked, or treated only as a reference implementation?
5. What capabilities are missing from current lightweight dbt lineage tools?
6. What information will the future test-lineage tool need that ordinary lineage tools do not currently expose?
7. Can the required information be extracted reliably through static analysis?
8. When is warehouse schema access necessary?
9. How should ambiguous and unsupported SQL be represented?
10. Should OpenLineage be supported as an export format?
11. What should be included in the MVP, and what should explicitly be deferred?
12. What would make this project independently useful rather than merely infrastructure for the test-lineage tool?

## Deliverables

Produce a research and design report containing:

### 1. Executive summary

Recommend the most promising direction and explain why.

### 2. Existing-tool comparison

Create a comparison matrix covering the investigated offerings and required capabilities.

### 3. Deep assessment of the strongest candidates

Inspect their APIs, architecture, source code, tests, limitations, maintenance, and suitability.

### 4. Gap analysis

Identify what existing offerings do not provide that our proposed tool should provide.

### 5. Recommended product scope

Define what the standalone column-lineage tool should and should not do.

### 6. Recommended architecture

Propose package boundaries, core abstractions, dependency choices, and a neutral lineage intermediate representation.

### 7. Build-versus-extend recommendation

Explicitly recommend whether to adopt, wrap, fork, combine, or build.

### 8. MVP plan

Propose a small first version that proves the most uncertain technical assumptions.

### 9. Evaluation plan

Design a representative fixture dbt project and test cases for evaluating lineage correctness across Snowflake SQL patterns.

### 10. Risks and unknowns

Highlight likely failure cases, technical limitations, maintenance risks, and questions requiring prototypes.

For important claims, link to primary sources such as official documentation, repositories, source files, tests, issues, and release history.

Where evidence is incomplete, say so rather than guessing.
