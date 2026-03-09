# Bundle Artifact — Specification

## Status

**PLANNED**

## Overview

This spec introduces the **bundle artifact** for `mdcc`: a single-file, SQLite-based compiled artifact that preserves the canonical source document together with the structured data, metadata, and execution outputs needed for agent inspection and reproducible rendering.

Today, `mdcc` is strongly agent-friendly at the **source** level, but the main compiled output is still a PDF, which is optimized for humans rather than agents. A PDF can be read by an agent, but it is a poor substrate for structured analysis, data exploration, or reuse of the datasets behind charts and tables. The bundle artifact fills that gap.

The bundle uses **SQLite as the container** for metadata and structure, stores **dataset payloads as serialized blobs** (Parquet), and uses **DuckDB as the analytical query engine** for SQL access to persisted datasets.

The bundle does **not** replace the plain-text source format. The source remains the canonical authored input and stays plain text / Git-friendly. The bundle is a separate compiled artifact intended for sharing, inspection, querying, and re-rendering.

---

# 1. Purpose

This spec adds a portable compiled artifact format (`.mdcx`) that allows agents and humans to inspect the canonical source, discover datasets and their schemas, query persisted tabular data with SQL, and render a final PDF from the artifact without requiring access to the original workspace state. The feature must preserve the existing `mdcc` principles: agent-first behavior, plain-text authored source, and a compiler-style workflow where a source document is compiled into a generated artifact.

---

# 2. Design Goals

## 2.1 Source fidelity

The canonical source stored in the bundle must be the exact authored source, unchanged and recoverable byte-for-byte.

## 2.2 Agent-readable inspection

Agents must be able to inspect the document, datasets, and relationships through stable CLI commands without reverse-engineering the PDF.

## 2.3 Queryable data access

Persisted tabular datasets must be queryable through SQL so that agents can perform exploratory analysis beyond the author’s intended views.

## 2.4 Single-file portability

The compiled artifact must be a single portable file that can be shared independently of the original repository or working directory.

## 2.5 Clean separation of authoring and artifact layers

The bundle must not become the authoring format; plain-text source remains the authored input and the bundle remains a compiled artifact.

## 2.6 Incremental rollout

The implementation must be phaseable. A useful MVP should ship before deeper inspection and provenance features are exposed.

## 2.7 Forward-compatible storage model

The SQLite schema should leave room for richer inspection, provenance, and persistence strategies later without breaking the phase 1 contract.

---

# 3. Scope

## 3.1 Applies to

This spec covers:

- the new `.mdcx` bundle artifact format
- SQLite-backed storage of canonical source, structural metadata, and persisted datasets
- CLI commands for bundle creation, inspection, dataset access, SQL querying, source extraction, and rendering from bundle
- persistence rules for which datasets are stored in the bundle
- inspection views derived from the bundle, including a source-preserving annotated view
- compatibility rules between the existing source compiler flow and the new bundle flow

## 3.2 Out of scope

This spec does **not** introduce:

- replacement of the plain-text `.mdcc` source format
- embedded PDF storage inside the bundle
- a `--json` CLI output mode
- SQL files as input to the SQL command
- a REPL or interactive shell
- external / remote bundle storage
- non-SQLite bundle formats
- blanket persistence of every intermediate dataframe created during execution
- phase 1 dedicated `section`, `block`, or `output` command groups
- mutation or rewriting of the canonical source stored in the bundle

---

# 4. Problem Statement

`mdcc` already satisfies the agent-first principle well at the **source** and **compiler** layers, but the current compiled output is optimized for human consumption. This creates a gap:

| Goal | Problem |
|------|---------|
| Agent-first | A PDF is difficult to inspect programmatically and does not expose the underlying data model directly. |
| Single-file compiled artifact | The source can reproduce the report, but the compiled output does not preserve the structured data and relationships needed for agent exploration. |
| Reproducibility | Re-rendering should not depend on hidden local state outside the compiled artifact. |
| Data exploration | An agent may want to ask new questions of bundled data that the original document did not explicitly answer. |
| Source correctness | Metadata helpful for agents should not be injected into the canonical source in ways that could affect compilation or rendering. |

This spec resolves the tension by introducing a separate bundle artifact layer:

- the authored source remains plain text and Git-friendly
- the bundle becomes the portable compiled artifact
- the bundle stores structured data and relationships in SQLite
- inspection output may be enriched, but the stored canonical source remains unchanged

---

# 5. Proposed Solution

## 5.1 Artifact model

The bundle artifact is a SQLite file with extension `.mdcx`.

It contains:

- the canonical source document exactly as authored
- normalized metadata about the document and compiler version
- persisted tabular datasets used by the document
- mappings between document blocks and persisted datasets
- enough execution metadata to support inspection and reproducible rendering from bundle

Conceptually, the system becomes:

- `*.mdcc`/`*.md` — authored source
- `*.mdcx` — compiled bundle artifact
- `*.pdf` — rendered human-facing output

The bundle is the machine-friendly compiled artifact. The PDF remains the human-facing rendered output.

## 5.2 Canonical source vs inspection projections

The bundle stores the **canonical source** exactly as authored.

The CLI may also expose **derived inspection projections**, such as an annotated source view that shows information like:

- dataset IDs linked to a block
- row counts
- column names
- persistence roles

These enriched views are computed from bundle contents at inspection time. They are **not** persisted as rewritten source and are never used as the canonical source for rendering.

## 5.3 Dataset persistence model

A block is not assumed to own exactly one dataset.

Instead:

- a block may reference or produce zero or more persisted datasets
- a persisted dataset may be linked to one or more blocks
- persisted datasets carry a role relative to a block

The initial supported roles are:

- `input` — data loaded from an external source (CSV, parquet, JSON, Excel, ...)
- `primary` — the main dataset used to render a chart or table
- `supporting` — additional dataset relevant to a rendered result

Later phases may add:

- `intermediate`
- `derived`
- `preview`

Phase 1 persists only datasets that are useful and discoverable by default. It does **not** persist every dataframe encountered during execution.

## 5.4 SQLite as the bundle container

SQLite is used as the **bundle container** because it provides:

- a single-file container
- mature, widely available tooling
- queryable storage for metadata and structural relationships
- efficient partial reads for agents
- a stable base for future schema evolution

SQLite stores all bundle metadata, document structure, dataset registry, and block-to-dataset mappings. Dataset payloads are stored as serialized blobs (Parquet) inside SQLite, not as dynamically created SQLite tables.

SQLite is **not** the SQL query engine for datasets. Dataset querying is handled by DuckDB (§5.4b).

## 5.4b DuckDB as the analytical query engine

DuckDB is used as the **SQL query engine** for dataset exploration. It powers `mdcc sql` and dataset preview commands.

DuckDB is chosen because:

- it is an embedded, in-process analytical engine — no server required
- it natively reads Parquet, Arrow, CSV, and JSON
- it provides a PostgreSQL-like SQL dialect suited to analytical queries
- it is columnar and optimized for the aggregation / filtering / joining workloads agents perform
- it integrates cleanly with Python and requires no system dependencies

The query flow for `mdcc sql` is:

1. open the SQLite bundle
2. resolve dataset references from the `datasets` registry
3. extract or memory-map dataset payloads from `dataset_payloads`
4. register each payload as a named DuckDB relation
5. execute the SQL query
6. return results

DuckDB is a runtime dependency for SQL execution and dataset preview commands. Bundle creation, metadata inspection, and source extraction do not require DuckDB.

## 5.4c Dataset payload storage

Dataset payloads are stored as **serialized blobs** inside the SQLite bundle rather than as dynamically created SQLite tables.

The default serialization format is **Parquet** because it:

- preserves column types, nullability, and schema faithfully
- handles nested and complex data structures (lists, dicts)
- is compact and widely supported
- round-trips pandas DataFrames without lossy type conversion

Datasets are stored in a dedicated `dataset_payloads` table with a blob column. The `datasets` registry table stores metadata (name, schema summary, row count, fingerprint) for fast lookups without extracting the payload.

This design avoids:

- dynamic SQL DDL generation for each dataset
- lossy type mapping between pandas dtypes and SQLite column types
- schema management complexity for nested or heterogeneous data
- pollution of the SQLite table namespace with dynamic dataset tables

## 5.5 Rendering from bundle

The bundle must support rendering to PDF without relying on the original workspace state.

For phase 1, this means the bundle contains:

- canonical source
- persisted data required by the rendered outputs
- enough metadata to reconstruct chart/table rendering inputs

The PDF itself is **not** embedded in the bundle.

## 5.6 Architecture integration

This feature should be integrated as a new artifact layer on top of the existing compiler pipeline, not as a second parser / executor stack.

The existing source-side stages should remain authoritative:

- `reader.py` reads canonical source bytes
- `parser.py` builds the `DocumentModel`
- `validator.py` performs structural validation and typed result validation
- `executor/` runs blocks in isolated subprocesses
- `renderers/` continue to own block rendering and document assembly
- `pdf.py` remains the only PDF generation layer

Bundle support should attach to those seams rather than bypass them.

### 5.6.1 Shared orchestration

`mdcc compile` and `mdcc bundle create` should share the same early pipeline through typed block results.

Recommended refactor:

- keep `compile.py` as the source-to-PDF orchestrator
- extract reusable helpers for document loading (`read` -> `parse` -> structure validation)
- extract reusable helpers for block materialization (`payload build` -> `execute/cache resolve` -> typed result validation)
- extract reusable helpers for rendering from typed block results

A useful shared internal shape is a per-block compiled record containing:

- the parsed block
- the execution payload
- the execution result
- the validated typed result
- dependency hashes / runtime manifests
- the rendered artifact when rendering was requested

This avoids duplicating pipeline logic between `compile`, `bundle create`, and later `render <bundle>`.

To stay consistent with the current architecture invariant, new cross-stage bundle record types should live in `src/mdcc/models.py`.

### 5.6.2 Bundle module boundary

The bundle implementation should live under a dedicated `src/mdcc/bundle/` package.

Recommended modules:

- `builder.py` — builds an in-memory bundle model from the parsed document and compiled block records
- `datasets.py` — extracts persisted datasets, computes fingerprints, and serializes payloads to Parquet
- `store.py` — owns SQLite DDL, inserts, reads, and schema-version helpers
- `validate.py` — validates bundle integrity and schema expectations
- `inspect.py` — produces human-readable bundle and annotated-source projections
- `sql.py` — registers dataset payloads in DuckDB and executes SQL
- `render.py` — renders a PDF from a bundle using the existing renderer and PDF modules

This keeps SQLite, DuckDB, inspection formatting, and source compilation concerns separated.

### 5.6.3 Runtime capture extension

The current execution prelude already records file dependencies. Bundle creation should extend the same mechanism with a second runtime manifest for dataset capture.

Recommended approach:

- extend `BuildContext` with deterministic paths for dataset manifests and temporary dataset payload files
- keep the prelude responsible only for observing runtime facts
- wrap supported pandas readers to record dataset captures in addition to file dependencies
- let host-side bundle code decide which captures become persisted bundle datasets

Phase 1a decision:

- dataset capture is enabled for `mdcc bundle create`, not for `mdcc compile`
- normal source compilation continues to track file dependencies from wrapped pandas readers, but it does not persist reader outputs to Parquet
- `mdcc bundle create` bypasses the block cache in phase 1a so bundle creation always materializes the dataset captures it needs directly from execution

Rationale:

- persisting reader outputs during ordinary `compile` introduced overhead and a failure mode unrelated to PDF generation: some valid pandas dataframes can be rendered normally but cannot be serialized to Parquet
- reusing compile cache entries for bundle creation is ambiguous when those cache entries were created without dataset capture enabled
- bypassing cache for bundle creation keeps phase 1a semantics simple while preserving the existing compile cache behavior

The prelude should not assign final bundle IDs or write SQLite directly. It should emit normalized capture facts such as:

- source kind (`read_csv`, `read_parquet`, etc.)
- normalized source path when one exists
- row / column metadata
- temporary payload location

Primary rendered datasets should be derived outside the prelude:

- table blocks can persist `TableResult.value` directly as the primary dataset
- chart blocks should use a dedicated extractor over `ChartResult.value` / `ChartResult.spec`

That keeps the execution sandbox simple and keeps bundle policy in normal Python modules instead of injected runtime code.

### 5.6.4 Render-from-bundle contract

Inspection and SQL querying can be satisfied by persisted datasets alone, but reproducible rendering cannot, especially for charts.

For `mdcc render <bundle>` to fit the current architecture cleanly, phase 1b should persist **semantic block outputs** in the bundle using the same boundary already used by the cache:

- charts: Vega-Lite / Altair spec JSON
- tables: the primary dataframe payload used for final table rendering

Recommended additional logical relations:

- `block_outputs(block_id, output_kind, format, payload_id)`
- `output_payloads(payload_id, blob_data)`

With that addition, bundle rendering becomes:

1. load canonical source and block metadata from SQLite
2. load semantic block outputs from the bundle
3. reuse existing block renderers to materialize `RenderedArtifact`s
4. reuse `renderers/document.py` for assembly and HTML generation
5. reuse `pdf.py` for final PDF creation

Without persisted semantic outputs, `render <bundle>` would require re-executing source blocks against a bundle-specific compatibility layer, which cuts across the current execution and rendering boundaries.

### 5.6.5 CLI and diagnostics fit

The CLI should remain thin and keep `cli.py` as the only presentation / exit-code boundary.

Recommended CLI shape:

- add `bundle`, `dataset`, and `extract` command groups via Typer sub-apps
- keep `inspect`, `sql`, and `render` as thin command adapters that delegate into dedicated modules
- keep terminal formatting centralized in `cli.py`

The diagnostics model should also be extended rather than overloaded. In addition to the current stages, bundle work will likely need dedicated typed errors for:

- bundle open / schema errors
- bundle validation errors
- inspection lookup errors
- SQL execution errors

That maps naturally to additional `DiagnosticStage`, `DiagnosticCategory`, and `MdccError` subclasses instead of reporting bundle failures as generic validation errors.

## 5.7 Rejected alternatives

### ZIP archive of text + data files

Rejected as the primary artifact format because it weakens structured querying, makes relationships more ad hoc, and creates more implicit conventions for agents to learn.

### Single giant JSON / YAML file

Rejected because large tabular data becomes unwieldy, random access is poor, and the artifact becomes both bloated and harder to query incrementally.

### Rewriting source with injected comments

Rejected because it couples inspection needs to source correctness and risks future rendering ambiguity. The source stored in the bundle must remain canonical and unchanged.

### Custom binary format

Rejected because it would require solving packaging, indexing, and schema evolution problems already handled well by SQLite.

### Datasets as dynamic SQLite tables

Rejected because dynamically creating one SQLite table per dataset introduces significant complexity: dynamic DDL generation, lossy type mapping from pandas dtypes to SQLite column types, poor handling of nested or complex data structures (lists, dicts in cells), and namespace pollution. Storing datasets as serialized Parquet blobs avoids all of these problems while preserving schema fidelity.

### SQLite as the SQL query engine for datasets

Rejected because SQLite is optimized for transactional workloads, not analytical queries. It lacks native support for columnar formats like Parquet, has limited analytical SQL capabilities, and would require complex virtual table implementations to query blob-stored datasets. DuckDB is purpose-built for this use case.

---

## 5.8 Summary: SQLite Tables vs. File-Backed + DuckDB

| Feature | Option A: SQLite Tables | Option B: File-Backed + DuckDB |
|---|---|---|
| **Best for** | Simple, flat, transactional data. | Analytical artifacts, nested data, agent exploration. |
| **Data Fidelity** | Lossy conversion to SQLite type model. | **High.** Preserved in data-native format (Parquet). |
| **Nested Data** | Awkward TEXT/BLOB mapping. | **Native.** Rich support for lists and objects. |
| **Complexity** | Simple ingestion via `to_sql`. | Orchestration layer to map blobs to DuckDB. |
| **Query Power** | General-purpose SQL. | **Advanced.** Columnar, filter/projection pushdown. |

**Decision:** `mdcc` chooses **Option B**. While `to_sql` makes SQLite ingestion easy, it forces the artifact into the wrong abstraction. File-backed storage with DuckDB better matches the analytical nature of agent-first research artifacts.

---

# 6. Phase Rollout

## Phase 1a — Bundle Core

Deliver a useful artifact that agents can inspect and query.

Delivers:

- SQLite-based `.mdcx` bundle creation
- canonical source stored exactly as authored
- bundle metadata and document manifest
- persisted datasets for wrapped input reads and primary rendered datasets
- dataset capture performed during `mdcc bundle create` execution only
- bundle creation bypasses block cache in phase 1a
- dataset schema, row count, and storage metadata
- mapping between blocks and datasets
- `mdcc bundle create`
- `mdcc bundle info`
- `mdcc bundle validate`
- `mdcc dataset list`
- `mdcc dataset show`
- `mdcc dataset schema`
- `mdcc dataset head`
- `mdcc sql <bundle> "..."`
- `mdcc extract source`
- `mdcc extract dataset`

## Phase 1b — Inspection & Rendering

Project richer views and support reproducible rendering.

Delivers:

- `mdcc inspect <bundle>`
- `mdcc inspect <bundle> --source`
- `mdcc inspect <bundle> --annotated`
- `mdcc render <bundle>` (PDF output)

## Phase 2 — Richer structural inspection

Make the artifact easier to navigate without requiring SQL.

Adds:

- dedicated `mdcc outline`
- dedicated `mdcc block list`
- dedicated `mdcc block show`
- dedicated `mdcc block source`
- optional dedicated `mdcc section list`
- optional dedicated `mdcc section show`
- richer annotated inspection views
- clearer visibility into block-to-dataset relationships

Does **not** require changing phase 1 bundle format fundamentals.

## Phase 3 — Provenance and persistence expansion

Deepen bundle introspection and persistence options.

Adds:

- richer provenance / lineage storage
- optional persistence of selected intermediates
- more explicit dataset roles (`intermediate`, `derived`)
- richer execution metadata and dependency reporting
- possible export improvements and dataset materialization controls

This phase must remain additive and must not invalidate phase 1 bundles.

---

# 7. Schema / Contract

## 7.1 Phase 1 CLI surface

| Command | Description |
|---------|-------------|
| `mdcc bundle create <source.mdcc> -o <bundle.mdcx>` | Create a SQLite bundle from source. |
| `mdcc bundle info <bundle.mdcx>` | Print high-level bundle summary. |
| `mdcc bundle validate <bundle.mdcx>` | Validate bundle integrity and schema expectations. |
| `mdcc inspect <bundle.mdcx>` | Print a human-readable overview of the bundle. |
| `mdcc inspect <bundle.mdcx> --source` | Print the canonical stored source. |
| `mdcc inspect <bundle.mdcx> --annotated` | Print a derived annotated view of the source. |
| `mdcc dataset list <bundle.mdcx>` | List persisted datasets. |
| `mdcc dataset show <bundle.mdcx> --id <dataset_id>` | Show dataset metadata summary. |
| `mdcc dataset schema <bundle.mdcx> --id <dataset_id>` | Show dataset schema. |
| `mdcc dataset head <bundle.mdcx> --id <dataset_id> --rows <n>` | Preview the first `n` rows of a dataset. |
| `mdcc sql <bundle.mdcx> "<sql>"` | Run a SQL query against the bundle. |
| `mdcc extract source <bundle.mdcx> -o <file.mdcc>` | Extract canonical source. |
| `mdcc extract dataset <bundle.mdcx> --id <dataset_id> -o <file.csv>` | Export a persisted dataset. |
| `mdcc render <bundle.mdcx> -o <file.pdf>` | Render a PDF from a bundle. |

Notes:

- No `--json` flag is supported in this spec.
- `mdcc sql` accepts a SQL string only.
- The existing source-based flow may continue to support `mdcc compile` for `.mdcc` input, but bundle interaction uses `bundle`, `inspect`, `dataset`, `sql`, `extract`, and `render`.

Example:

```bash
mdcc bundle create report.mdcc -o report.mdcx
mdcc inspect report.mdcx
mdcc dataset list report.mdcx
mdcc dataset head report.mdcx --id ds_sales --rows 20
mdcc sql report.mdcx "select region, sum(revenue) as revenue from ds_sales group by region order by revenue desc limit 10"
mdcc render report.mdcx -o report.pdf
```

## 7.2 Phase 1 bundle schema

The exact SQL DDL may evolve, but phase 1 must satisfy the following logical contract.

### `bundle_meta`

Single-row metadata table.

| Field | Type | Required | Description |
|------|------|----------|-------------|
| `format_version` | string | yes | Bundle format version. |
| `created_at` | string | yes | Bundle creation timestamp. |
| `mdcc_version` | string | yes | Compiler version that produced the bundle. |
| `source_filename` | string | no | Original source filename if known. |
| `source_sha256` | string | yes | Hash of canonical source bytes. |

### `documents`

Stores the canonical document payload.

| Field | Type | Required | Description |
|------|------|----------|-------------|
| `document_id` | string | yes | Stable internal document ID. |
| `title` | string | no | Parsed title if available. |
| `source_text` | text | yes | Exact canonical source. |

### `blocks`

Stores block-level structural entries known at bundle creation time.

| Field | Type | Required | Description |
|------|------|----------|-------------|
| `block_id` | string | yes | Stable block ID. |
| `block_type` | string | yes | Block kind, e.g. chart/table/code subtype. |
| `source_start_line` | integer | yes | Start line in canonical source. |
| `source_end_line` | integer | yes | End line in canonical source. |
| `label` | string | no | User-declared label if present. |
| `caption` | string | no | User-declared caption if present. |

### `datasets`

Stores one row per persisted dataset.

| Field | Type | Required | Description |
|------|------|----------|-------------|
| `dataset_id` | string | yes | Stable dataset ID. |
| `name` | string | yes | Human-readable stable SQL-visible name used in DuckDB queries. |
| `format` | string | yes | Serialization format of the payload. Phase 1: `parquet`. |
| `role_summary` | string | yes | Summary of roles this dataset plays. |
| `row_count` | integer | yes | Number of rows. |
| `column_count` | integer | yes | Number of columns. |
| `source_kind` | string | yes | E.g. `read_csv`, `read_parquet`, `render_primary`, `manual_persist`. |
| `payload_id` | string | yes | References `dataset_payloads.payload_id`. |
| `fingerprint` | string | yes | Dataset content fingerprint. |

### `dataset_columns`

Stores schema information.

| Field | Type | Required | Description |
|------|------|----------|-------------|
| `dataset_id` | string | yes | Owning dataset. |
| `ordinal` | integer | yes | Column order. |
| `column_name` | string | yes | Column name. |
| `logical_type` | string | yes | Normalized logical type. |
| `nullable` | boolean | yes | Whether nulls are allowed / observed. |

### `block_datasets`

Maps blocks to datasets.

| Field | Type | Required | Description |
|------|------|----------|-------------|
| `block_id` | string | yes | Referencing block. |
| `dataset_id` | string | yes | Linked dataset. |
| `role` | string | yes | `input`, `primary`, or `supporting`. |

### `dataset_payloads`

Stores serialized dataset content as blobs.

| Field | Type | Required | Description |
|------|------|----------|-------------|
| `payload_id` | string | yes | Stable payload ID. |
| `blob_data` | blob | yes | Serialized dataset content (e.g. Parquet bytes). |

The `datasets.payload_id` field references this table. A payload may be shared by multiple dataset entries if the underlying data is identical (deduplication).

At query time, `mdcc sql` extracts the blob, registers it as a named DuckDB relation using the `datasets.name` field, and executes the query. Example names visible in DuckDB:

- `ds_sales`
- `ds_fig_revenue_primary`
- `ds_regions_lookup`

### `block_outputs` *(required for phase 1b rendering support)*

Stores the semantic render input for a block.

| Field | Type | Required | Description |
|------|------|----------|-------------|
| `block_id` | string | yes | Owning block. |
| `output_kind` | string | yes | Semantic output kind, e.g. `chart_spec`, `table_frame`. |
| `format` | string | yes | Serialization format, e.g. `vega_json`, `parquet`. |
| `payload_id` | string | yes | References `output_payloads.payload_id`. |

These outputs are distinct from persisted datasets. They exist so `mdcc render <bundle>` can reuse the existing rendering pipeline without re-executing block code.

### `output_payloads` *(required for phase 1b rendering support)*

Stores serialized semantic block outputs as blobs.

| Field | Type | Required | Description |
|------|------|----------|-------------|
| `payload_id` | string | yes | Stable payload ID. |
| `blob_data` | blob | yes | Serialized output payload. |

### Example

Minimal logical example:

```text
bundle_meta:
  format_version = 1
  source_sha256 = "..."

documents:
  document_id = "doc_main"
  source_text = "# Revenue Report\n..."

blocks:
  - block_id = "fig_revenue"
    block_type = "mdcc_chart"
    source_start_line = 18
    source_end_line = 34
    label = "fig:revenue"

datasets:
  - dataset_id = "dset_001"
    name = "ds_sales"
    format = "parquet"
    role_summary = "input,primary"
    row_count = 1248
    column_count = 4
    source_kind = "read_csv"
    payload_id = "payload_001"

dataset_payloads:
  - payload_id = "payload_001"
    blob_data = <parquet bytes>

block_datasets:
  - block_id = "fig_revenue"
    dataset_id = "dset_001"
    role = "primary"
```

## 7.3 Phase 2 additions

| Field / Option | Type | Required | Description |
|----------------|------|----------|-------------|
| `mdcc outline <bundle.mdcx>` | command | yes | Print document structure / TOC-style view. |
| `mdcc block list <bundle.mdcx>` | command | yes | List blocks. |
| `mdcc block show <bundle.mdcx> --id <block_id>` | command | yes | Show block metadata and linked datasets. |
| `mdcc block source <bundle.mdcx> --id <block_id>` | command | yes | Show exact source text for a block. |
| `sections` table *(optional)* | relation | no | Dedicated structural section table if implemented. |

## 7.4 Phase 3 additions

| Field / Option | Type | Required | Description |
|----------------|------|----------|-------------|
| `dataset_role = intermediate` | enum | no | Persisted intermediate dataset role. |
| `dataset_role = derived` | enum | no | Persisted derived dataset role. |
| provenance relations | relation | no | Richer upstream/downstream relationships. |
| persistence strategy flags | CLI option | no | Future controls for intermediate persistence. |

---

# 8. Validation Rules

## 8.1 Bundle file

- A bundle must be a readable SQLite database.
- A bundle must contain the minimum required phase 1 tables.
- `bundle_meta.format_version` must be supported by the current compiler version.

Invalid example:

```text
report.mdcx is a plain text file or a malformed SQLite database
```

Expected diagnostic:

```text
invalid bundle: file is not a readable SQLite database
```

## 8.2 Canonical source

- The bundle must contain exactly one canonical source payload.
- `source_sha256` must match the stored canonical source bytes.
- The canonical source must never be replaced by an annotated or enriched variant.

Invalid example:

```text
bundle_meta.source_sha256 does not match documents.source_text
```

Expected diagnostic:

```text
invalid bundle: canonical source hash does not match stored source text
```

## 8.3 Dataset identity

- Every dataset ID must be unique.
- Every SQL-visible dataset name must be unique.
- Every `datasets.payload_id` must reference an existing `dataset_payloads` row.
- Every payload blob must be a valid file in the declared `format` (e.g. readable Parquet).

Invalid example:

```text
datasets.payload_id = payload_001
but dataset_payloads has no row with payload_id = payload_001
```

Expected diagnostic:

```text
invalid bundle: persisted dataset 'ds_sales' references missing payload 'payload_001'
```

## 8.4 Block ↔ dataset mapping

- Every `block_datasets.block_id` must resolve to an existing block.
- Every `block_datasets.dataset_id` must resolve to an existing dataset.
- `role` must be one of the roles supported by the bundle format version.

Invalid example:

```text
block_datasets:
  block_id = fig_revenue
  dataset_id = dset_missing
  role = primary
```

Expected diagnostic:

```text
invalid bundle: block-to-dataset mapping references unknown dataset 'dset_missing'
```

## 8.5 CLI arguments

- `mdcc sql` must receive a SQL string argument.
- SQL file input is invalid in this spec.
- `mdcc render <bundle> -o ...` must resolve to PDF output.
- `mdcc dataset show/schema/head` must fail when the dataset ID does not exist.

Invalid example:

```bash
mdcc sql report.mdcx --file query.sql
```

Expected diagnostic:

```text
unsupported option: SQL file input is not supported; pass the SQL query as a string argument
```

## 8.6 Phase-specific behavior

- Phase 1 implementations must not claim support for dedicated `block`, `section`, or `output` command groups.
- Phase 1 annotated inspection output must be derived from bundle contents and must not mutate bundle source.

---

# 9. Diagnostics

Diagnostics must include:

- stage / category
- human-readable message
- source location when applicable
- enough context for an agent to recover automatically when possible

Examples introduced by this spec:

- `invalid bundle: file is not a readable SQLite database`
- `invalid bundle: unsupported bundle format version '2'`
- `invalid bundle: canonical source hash does not match stored source text`
- `invalid bundle: missing required table 'datasets'`
- `invalid bundle: persisted dataset 'ds_sales' is missing its SQLite payload table`
- `unknown dataset id: dset_missing`
- `unknown block id: fig_revenue`
- `unsupported option: SQL file input is not supported; pass the SQL query as a string argument`
- `render_error` — rendering from bundle failed

Recommended diagnostic categories:

- `bundle_error` — malformed or unreadable bundle
- `bundle_validation_error` — internal contract violation within a readable bundle
- `inspection_error` — object requested by the user does not exist or cannot be displayed
- `sql_error` — invalid SQL or SQL execution failure

---

# 10. Implementation Roadmap

This section defines the discrete implementation tasks for completing the bundle artifact features.

## 10.1 Phase 1b — Projects & Rendering

### BT-01: Inspect Commands (DONE)
Implement the `mdcc inspect` command group.
- **Scope**: `mdcc inspect <bundle>` (overview), `--source` prints canonical source, `--annotated` prints source with read-time dataset overlays.
- **Notes**: Derived projection only; no source mutation.

### BT-02: Render from Bundle (DONE)
Implement `mdcc render <bundle> -o <file.pdf>`.
- **Scope**: Extend schema with `block_outputs` and `output_payloads`. Store Vega-Lite/Parquet semantic outputs during creation. Render by feeding these outputs into existing renderers.
- **Notes**: Feature-detect `block_outputs` table presence in the bundle.

## 10.2 Phase 2 — Navigation

### BT-03: Block and Outline Navigation
Implement `mdcc block` group and `mdcc outline`.
- **Scope**: Table-of-contents view with blocks interspersed. Block listing, detail view, and source-level slicing.
- **Notes**: No schema changes; pure navigation and formatting work.

### BT-04: Annotated View Enrichment
Enrich the BT-01 annotated view with deeper relationship metadata.
- **Scope**: Show columns, fingerprints, and row counts inline for all linked datasets.

## 10.3 Phase 3 — Provenance & Persistence

### BT-05: Provenance Layer
Persist execution stats and lineage in the bundle.
- **Scope**: New tables `block_provenance` and `execution_stats`. Capture file dependency hashes and execution timing.
- **Notes**: Additive tables; detected at runtime.

### BT-06: Intermediate Dataset Persistence
Allow explicit opt-in for persisting mid-block DataFrames.
- **Scope**: `--persist-intermediates` flag. Update prelude to serialize mid-run captures. Add `intermediate` and `derived` roles.
- **Notes**: No new tables; additive enum roles in existing tables.
