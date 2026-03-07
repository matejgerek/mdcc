# mdcc Compiler Usage and Failure Interpretation

This document provides a guide for invoking the `mdcc` compiler, understanding its inner stages, interpreting common diagnostic failures, and managing its temporary build artifacts.

---

## 1. Running the Compiler

The `mdcc` application converts a solitary plain-text source file (.md) directly into a complete PDF report. 

You execute the compiler using its unified `compile` command:

```bash
mdcc compile <input_file> [output_file] [OPTIONS]
```

### Arguments:
*   `input_file`: Path to the markdown source file (Required).
*   `output_file`: Path to the generated PDF. If omitted, the compiler defaults to creating `<input>.pdf` adjacent to the input file.

### Options:
*   `--timeout <seconds>`, `-t`: Overrides the default execution time allowed per block (default is 30.0 seconds).
*   `--keep-build-dir`: Prevents the compiler from deleting the intermediate `.mdcc_build` directory post-completion. This is extremely useful for manual debugging.
*   `--no-cache`: Disables the persistent per-block cache and forces fresh execution for every block.
*   `--verbose`, `-v`: Elevates diagnostic output detail if the compilation fails. It will also display a success message when finishing gracefully.

For a dry-run validation pass that stops before payload generation, execution, rendering, and PDF output, use:

```bash
mdcc validate <input_file>
```

This command reads, parses, and validates the document, then prints a human-readable validation report. It exits `0` when the document is valid and `1` when read, parse, or validation errors are detected.

---

## 2. High-Level Compiler Stages

The `mdcc` compilation process isn't a single magical step. Under the hood, the document passes through an explicit sequence of stages:

1.  **Read Stage**: Loads the source file into memory.
2.  **Parse Stage**: Separates frontmatter, standard markdown text, and explicitly fenced executable blocks (`mdcc_chart` and `mdcc_table`).
3.  **Validation Stage (Structural)**: Checks if blocks are properly closed and if their requested types are recognized by the system MVP.
4.  **Cache Resolution Stage**: Computes block fingerprints, checks `.mdcc_cache/`, validates dependency manifests, and decides whether the block can reuse cached outputs.
5.  **Execution Stage**: Runs cache misses sequentially from top to bottom. Each block evaluates in its own **completely isolated Python process** with pre-loaded data tools (`pandas`, `numpy`, Altair).
6.  **Validation Stage (Typed Output)**: Assures that the captured final expression result perfectly matches the block's promised contract (e.g., Altair Chart, Pandas DataFrame).
7.  **Rendering Stage**: Maps semantic outputs (tables or charts) to their target visual representations (HTML fragments, SVG artifacts). Cached semantic results may also be re-rendered here if the artifact fingerprint changed.
8.  **Assembly Stage**: Interleaves the processed execution artifacts seamlessly with the standard markdown narrative.
9.  **PDF Generation Stage**: Compiles the unified assembly into the final PDF.

---

## 3. Cache Behavior

Phase 1 caching is local, persistent, and scoped to the source directory.

*   **Cache location**: `.mdcc_cache` next to the source document.
*   **What is reused**: successful per-block semantic results and block-local rendered artifacts.
*   **What always runs fresh**: document assembly, cross-reference resolution, and PDF generation.
*   **What invalidates the cache**: block definition changes, runtime fingerprint changes, or changes to tracked local filesystem reads.

The compiler records best-effort local file dependencies during execution by tracking:

*   `open(...)`
*   `pd.read_csv(...)`
*   `pd.read_json(...)`
*   `pd.read_excel(...)`
*   `pd.read_parquet(...)`

Dependency validity is based on file **content hashes**. File size or modification time may be used as internal shortcuts, but correctness is decided by content hashing.

Phase 1 does **not** guarantee correct invalidation for:

*   HTTP/network reads
*   time/randomness
*   environment variables
*   external services
*   other hidden ambient state

Use `--no-cache` when you want to bypass cached results entirely.

---

## 4. Failure Categories

When `mdcc` encounters an error, it interrupts compilation immediately instead of outputting an incomplete or visually broken document. The failure is broadly categorized into one of these buckets:

*   **Read Error (`READ_ERROR`)**: Triggered when the input source file is missing, empty, or unreadable due to filesystem permissions.
*   **Parse Error (`PARSE_ERROR`)**: Triggered when the markdown format is fundamentally broken (e.g., malformed code blocks or heavily distorted frontmatter).
*   **Validation Error (`VALIDATION_ERROR`)**: Arises when the overall structure is poor (e.g. unknown block types) OR an executable block returns a data type that breaks its own contract (e.g., an `mdcc_chart` returned a pandas data frame). 
*   **Execution Error (`EXECUTION_ERROR`)**: Triggered by a runtime exception raised inside the Python block itself (e.g., `KeyError` on a dataframe layer).
*   **Timeout Error (`TIMEOUT_ERROR`)**: Triggered if a specific block runs longer than the allowed `--timeout` constraint (usually an infinite loop or heavy computation). 
*   **Rendering Error (`RENDERING_ERROR`)**: Arises when an explicitly returned object is valid in type but fails to be mapped to an output visual (e.g. invalid arguments passed to a core charting library).
*   **PDF Generation Error (`PDF_ERROR`)**: Raised when the internal HTML rendering mechanism fails while converting the assembled output to the PDF document. 

---

## 5. Interpreting Block Diagnostics

The most frequent errors you will encounter will be `ExecutionError` or `ValidationError` inside your execution blocks. By design, the compiler will provide deterministic and highly readable context when these happen.

### Basic Diagnostic Structure:
A terminal-formatted compiler error looks like this:

```
error: The chart block crashed at execution.
  stage: execution
  file: input.md
  block: #3 (mdcc_chart)
  location: lines 10:1-15:3
```

### Verbose Mode (`--verbose`):
Enabling the verbose flag expands the diagnostic snapshot significantly, adding properties that are indispensable for autonomous coding agents:

*   **category**: The exact exception class category.
*   **expected / actual**: Highly actionable typing mismatches (e.g., expected `Altair Chart`, got `NoneType`).
*   **stderr / stdout**: Any manual `print()` statements evaluating inside that specific block right up until the point of panic.
*   **caused by**: The raw original Python exception that caused the engine crash.
*   **cache status**: Informational lines such as `cache hit`, `cache miss`, or `cache bypassed` for each executable block during successful compiles.

**Interpreting logs vs exports:** Remember that printed output (`stdout`) never renders onto the PDF. However, you should still actively harness `print()` strings for visibility when debugging your logic, checking it via compiler diagnostics.

---

## 6. Temporary and Persistent Build Artifacts

During the compilation process, `mdcc` produces both ephemeral build artifacts and persistent cache artifacts.

### `.mdcc_build`

*   **Where**: `.mdcc_build` is created next to the source document.
*   **What it contains**: payload scripts, execution logs, temporary result envelopes, dependency logs, and per-run rendered artifacts.
*   **Default behavior**: `mdcc` removes `.mdcc_build` automatically after compilation ends.
*   **Debugging**: Passing `--keep-build-dir` keeps the directory for inspection.

### `.mdcc_cache`

*   **Where**: `.mdcc_cache` is also created next to the source document.
*   **What it contains**: persistent per-block cache entries, dependency manifests, cached semantic results, and cached block-local rendered artifacts.
*   **Default behavior**: `.mdcc_cache` is preserved across runs.
*   **Bypass**: Passing `--no-cache` leaves existing cache entries untouched but disables cache lookup and cache writes for that compile.
