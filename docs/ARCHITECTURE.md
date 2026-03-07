# Architecture

This document describes the high-level architecture of `mdcc`.
If you want to familiarize yourself with the codebase, you are in the right place.

For context on *why* the project exists and the philosophy behind its design, see `docs/DESIGN_PRINCIPLES.md`.
For the source document format and block syntax, see `docs/SOURCE_FORMAT.md`.
For CLI usage, see `docs/COMPILER_USAGE.md`.

---

## Bird's Eye View

`mdcc` is a **compiler**: it takes a single plain-text source file containing markdown prose and fenced executable Python blocks, and produces a single PDF artifact.

The source document is the canonical definition of the report. The compiler runs the executable blocks in isolation, validates their outputs, renders the results into visual artifacts (charts and tables), and assembles everything into a final PDF. The PDF is entirely derived from the source; it is never edited directly.

The compiler is designed to be **agent-first**. The format, execution model, and diagnostics are optimized for coding agents that generate, edit, and debug documents via CLI and files — not for interactive notebook-style editing.

---

## Code Map

The project follows the standard `src/` layout. All application code lives under `src/mdcc/`.

### `src/mdcc/cli.py` — Entry Point

The CLI surface implemented with `typer`. This is the **entry point** for all user and agent interaction. It exposes two commands:

- `mdcc compile` — runs the full compilation pipeline.
- `mdcc validate` — validates document structure without executing blocks.

The CLI parses options into a `CompileOptions` model and delegates to `compile.py`. It is also the **only place** where errors are caught and formatted for terminal output.

**Architecture Invariant:** `cli.py` is the only module that interacts with the process exit code and standard error output. No other module should call `typer.echo` or `sys.exit`.

### `src/mdcc/compile.py` — Pipeline Orchestrator

`compile.py` is the top-level orchestrator. The `compile` function wires together all pipeline stages in order. It is the clearest place to understand the full flow:

1. Read → 2. Parse → 3. Validate Structure → 4. Build Payloads → 5. Resolve Cache or Execute → 6. Validate Result Types → 7. Render Artifacts → 8. Assemble Document → 9. Render HTML → 10. Generate PDF

`CompileOptions` is the typed settings object forwarded from the CLI.

### `src/mdcc/models.py` — Domain Model

**This is the most important file to understand first.** It defines every data structure that flows between pipeline stages. All stage boundaries use types from `models.py` — nothing inside one stage bleeds into another except through these types.

Key types and the boundaries they represent:

- `SourceDocumentInput` — output of `reader.py`, input to `parser.py`
- `DocumentModel` — output of `parser.py`, input to `validator.py` and `executor/`
- `ExecutionPayload` — output of `executor/payload.py`, input to `executor/runner.py` and `cache.py`
- `BlockExecutionResult` — output of `executor/runner.py`, input to `validator.py` (result validation)
- `TypedBlockResult` (= `ChartResult | TableResult`) — output of `validator.py`, input to `renderers/`
- `RenderedArtifact` — output of `renderers/`, input to `renderers/document.py` (assembly)
- `AssembledDocument` — output of `renderers/document.py`, input to `renderers/document.py` (HTML rendering)
- `IntermediateDocument` — output of HTML rendering, input to `pdf.py`
- `Diagnostic` — the structured error record; every `MdccError` carries one

**Architecture Invariant:** `models.py` has no application logic. It only defines data shapes. No module in the pipeline imports from another pipeline stage — they communicate exclusively through types from `models.py`.

### `src/mdcc/reader.py` — Source Reader

Reads the raw `.mdcc` source file from disk and splits it into a YAML frontmatter section and a markdown body. Produces `SourceDocumentInput`.

### `src/mdcc/parser.py` — Block Parser

A hand-written line-by-line parser. It walks the body text and distinguishes:

- Fenced executable blocks (info string starts with `mdcc_`) — parsed into `ExecutableBlockNode`
- Everything else (including regular code fences for display) — accumulated into `MarkdownNode`

The parser is the only place where `ExecutableBlockNode` objects are created. It records source spans (`SourceSpan`, `SourceLocation`) for every node so later diagnostics can point to the right line.

**Architecture Invariant:** the parser never executes any code. It is purely structural — it understands fences and attributes, but knows nothing about Python syntax, Altair, or pandas.

**Architecture Invariant:** an unclosed executable fence is a hard parse error. The parser produces either a valid `DocumentModel` or raises `ParseError`. It never silently drops blocks.

### `src/mdcc/validator.py` — Validator

Two distinct validation responsibilities live here:

1. **Document structure validation** (`validate_document_structure`, `assert_valid_document_structure`): checks that the parsed `DocumentModel` is structurally sound — unique node IDs, sequential block indices, valid metadata attributes, no duplicate labels, no unresolved cross-references.

2. **Result type validation** (`validate_typed_result`, `assert_valid_typed_result`): after execution, checks that each block's raw output is the correct type for its block kind (`mdcc_chart` → Altair chart; `mdcc_table` → `pd.DataFrame`), and coerces it into the appropriate `TypedBlockResult`.

3. **Runtime policy validation** (`validate_executable_block_runtime_policy`): checks that block code satisfies the execution sandbox contract — no `import` statements or dynamic `__import__` calls.

**Architecture Invariant:** validation is side-effect-free. No files are written, no subprocesses are launched.

### `src/mdcc/executor/` — Isolated Block Execution

The executor module is responsible for running each executable block in a fresh Python subprocess. It has four components:

- **`payload.py`** — builds execution scripts. For each `ExecutableBlockNode`, it assembles a complete Python script: prelude + user code (with the final expression rewritten for capture) + epilogue. The script is written to `.mdcc_build/payloads/`.

- **`prelude.py`** — the fixed runtime environment injected ahead of every user block. The prelude makes `pd`, `np`, and `alt` available without user imports. It also installs the dependency-tracking wrappers: `open()` and `pd.read_*` are monkey-patched to record file paths accessed in read mode into a dependency manifest. The epilogue serializes the final expression result to `MDCC_RESULT_PATH` via pickle.

- **`runner.py`** — launches the assembled script in a `subprocess.run` call and collects `stdout`, `stderr`, exit code, and timing. Returns `BlockExecutionResult` on success; raises `ExecutionError` or `TimeoutError` on failure.

- **`result.py`** — reads the pickled result envelope written by the epilogue.

**Architecture Invariant:** each block runs in a completely fresh Python interpreter. There is no shared globals, no shared interpreter state, and no communication between blocks at runtime.

**Architecture Invariant:** the executor module has no rendering or PDF logic. It produces a `BlockExecutionResult`. Rendering is a separate concern.

**Architecture Invariant:** the prelude is the only place where the ambient execution environment is defined. User code cannot import additional libraries. If a library is not in the prelude, it is not available.

### `src/mdcc/cache.py` — Block Cache

The cache stores the results of expensive block executions so they can be reused on subsequent compilations. It is a **per-block, per-source-directory**, file-based cache stored in `.mdcc_cache/` next to the source file.

A cache entry consists of:

- A `CacheManifest` (JSON) — fingerprints, dependency list, file references, timing, and shape metadata.
- A **semantic artifact** — the raw result in a stable serialization: `spec.json` for charts (Altair Vega-Lite spec), `table.pkl` for tables (pickled DataFrame).
- A **rendered artifact** — the final rendered output: `rendered.svg` for charts, `rendered.html` for tables.

The cache uses two fingerprints:

- **Execution fingerprint** (`build_execution_fingerprint`): a hash of the block code, block type, capture mode, runtime prelude template, mdcc version, Python version, and execution working directory. A cache hit on this fingerprint means the block can be skipped entirely.
- **Artifact fingerprint** (`build_artifact_fingerprint`): derived from the execution fingerprint, artifact kind, and a hash of the renderer source code. A mismatch here means the semantic result is valid but the rendered artifact needs to be regenerated (e.g., renderer changed without code changing).

Cache resolution has three outcomes (visible in `CacheStore.resolve_artifact`):
- **miss** — no valid entry; block must execute.
- **hit / artifact reused** — both fingerprints match and rendered file exists; return the cached artifact directly.
- **hit / artifact refreshed** — execution fingerprint matches but artifact fingerprint changed; re-render from the cached semantic result without re-executing.

**Architecture Invariant:** the cache is **semantic-first, not occurrence-first**. Two blocks with identical code in the same document share one cache entry. The cache key does not include block index or node ID. Any future requirement for strict per-occurrence isolation would require a new identity layer in the lookup key.

**Architecture Invariant:** cache reuse stops at the rendered-artifact boundary. Document assembly and PDF generation are always fresh. The cache only covers block execution and block-level rendering.

**Architecture Invariant:** dependency invalidation covers only the tracked surface: `open()` (read modes) and `pd.read_csv`, `pd.read_json`, `pd.read_excel`, `pd.read_parquet`. Network reads, time, environment variables, and other ambient state are outside the cache guarantee. `Path.read_text()`, `Path.read_bytes()`, and `Path.open()` are also not currently tracked.

### `src/mdcc/references.py` — Cross-Reference System

Cross-references let markdown prose mention labeled executable blocks. Labels are declared as a metadata attribute on a block's fence (`label="fig1"`), and referenced in markdown with `@fig1` syntax. The reference expands to a human-readable text like "Figure 1" or "Table 2".

`references.py` provides:
- `build_reference_registry` — maps label strings to `ResolvedReference` objects (including ordinal counters by block type).
- `iter_reference_labels_in_markdown` — walks the mistune AST to find all `@label` occurrences in markdown text.

The validator checks references at parse time. The document renderer (`renderers/document.py`) resolves them at render time.

### `src/mdcc/renderers/` — Artifact and Document Rendering

Three components:

- **`chart.py`** — converts an Altair chart object (or its Vega-Lite spec dict) into an SVG file using `vl-convert-python`. Writes the file to `.mdcc_build/charts/`.

- **`table.py`** — converts a `pd.DataFrame` into an HTML table fragment using pandas' built-in `.to_html()`. Writes the file to `.mdcc_build/tables/`.

- **`document.py`** — assembles the final HTML document. First it interleaves `MarkdownNode`s and `RenderedArtifact`s in document order (`assemble_document`). Then it renders the assembled document to a full HTML string (`render_intermediate_document`), resolving cross-references and rendering markdown via mistune. The HTML template is a Jinja2 template embedded directly in this file.

**Architecture Invariant:** `document.py` is the only module that knows about the relationship between markdown nodes and artifacts in document order. No other module assembles or re-orders the document nodes.

### `src/mdcc/pdf.py` — PDF Generation

A thin wrapper around WeasyPrint. Takes an `IntermediateDocument` (full HTML string + base path for resolving relative asset URLs) and writes the final PDF to disk.

**Architecture Invariant:** `pdf.py` knows nothing about blocks, execution, or rendering. It only consumes an HTML string.

### `src/mdcc/errors.py` — Diagnostics Model

All errors in the compiler are `MdccError` subclasses. Every `MdccError` carries a `Diagnostic` that captures stage, category, source location, block identity, stdout/stderr, and exception details. Concrete subclasses (`ReadError`, `ParseError`, `ValidationError`, `ExecutionError`, `TimeoutError`, `RenderingError`, `PdfGenerationError`) each declare their `DiagnosticStage` and `DiagnosticCategory`.

`format_diagnostic` produces a human-readable, structured error message for terminal output.

`DiagnosticCollector` accumulates multiple `Diagnostic` objects and can raise a single error from the collection. This is used in structural validation where multiple issues can be found in a single pass.

**Architecture Invariant:** every error that crosses a module boundary is a `MdccError` with a fully populated `Diagnostic`. No raw Python exceptions (other than within a module's internal implementation) should propagate to the CLI.

### `src/mdcc/validate.py` — Standalone Validation Command Adapter

A thin adapter that wires the `validate` CLI command to `reader.py` and `validator.py` without invoking the executor. Produces a human-readable validation report via `format_validation_report`.

### `src/mdcc/utils/workspace.py` — Build Directory

`BuildContext` manages the temporary `.mdcc_build/` directory created adjacent to the source file during a compilation run. It provides deterministic path helpers for every intermediate artifact type: payload scripts, result envelopes, dependency manifests, execution logs, chart images, and table HTML fragments.

**Architecture Invariant:** all intermediate files written during a compilation run go into `BuildContext`-managed paths. No pipeline stage writes files at arbitrary locations. The build directory is cleaned up on successful exit (unless `--keep-build-dir` is passed).

---

## Cross-Cutting Concerns

### Error Propagation

Every pipeline stage raises a typed `MdccError` subclass with a structured `Diagnostic` attached. The CLI (`cli.py`) is the single catch point: it catches `MdccError` and calls `format_diagnostic`, or falls through to `format_unexpected_error` for unexpected exceptions. No other module formats errors for the terminal.

Diagnostics carry `DiagnosticStage` so that any error can be attributed to the exact compilation phase where it occurred (read, parse, validation, execution, timeout, rendering, pdf).

### Dependency Tracking

The execution prelude (`executor/prelude.py`) monkey-patches `builtins.open` and selected `pd.read_*` functions to record file paths accessed in read mode. These paths are written to a dependency manifest (`dependency_path`) by an `atexit` handler at the end of each block's subprocess. After execution, the compiler reads this manifest and hashes the referenced files. The hashes are stored in the cache entry. On subsequent cache lookups, any change to a tracked file causes a cache miss and re-execution.

This mechanism is **best-effort**: it only covers the explicitly patched surface. File reads via `Path.read_text()`, network calls, `os.environ`, and other implicit state are not tracked.

### Testing

Tests live in `tests/` and use `pytest`. Each major module has a corresponding test file. The test suite is designed to be entirely self-contained — no network access, no real installed Python packages beyond the project's own dependencies.

Key test files and what they cover:
- `test_parser.py` — block parsing, fence handling, metadata attributes, error cases
- `test_validator.py` — structural validation, runtime policy, result type validation
- `test_executor.py` — payload assembly, subprocess execution, timeout, result extraction
- `test_cache.py` — fingerprinting, cache resolution paths (miss / hit / refresh), dependency invalidation
- `test_renderers.py` — chart SVG generation, table HTML generation, document assembly, reference resolution
- `test_result_extraction.py` — epilogue rewriting, final expression capture, unpicklable value handling
- `test_e2e.py` — end-to-end compilation from `.mdcc` source to PDF
- `test_cli.py` — CLI command wiring, exit codes, error formatting
- `test_diagnostics.py` — `Diagnostic` model, `format_diagnostic` output

### Build Directory Lifecycle

The `.mdcc_build/` directory is the working scratchpad for a single compilation run. It is created at the start of `compile()`, used by all pipeline stages, and deleted on exit (unless `--keep-build-dir` is set). It is never committed to version control and is not safe to share between concurrent compilations of the same source file.

The `.mdcc_cache/` directory is the persistent, long-lived cache store. It is committed to `.gitignore` by convention but is intentionally preserved across runs.
