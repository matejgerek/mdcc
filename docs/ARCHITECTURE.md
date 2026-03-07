# mdcc — Software Architecture and Directory Structure

This document outlines the high-level architecture and directory structure for `mdcc` (Agent-First Executable Report Compiler), based on the MVP and feature specifications in `docs/features/` and the implementation tasks in `TASKS.md`.

## High-Level Architecture

The compiler acts as a linear, deterministic pipeline that transforms a single source text file containing markdown and executable blocks into a single PDF artifact. 

The pipeline is composed of the following core stages:

1. **CLI / Orchestrator**: The entrypoint that parses CLI arguments, orchestrates the compilation pipeline, and presents human-readable diagnostics.
2. **Reader & Parser**: Reads source files, extracts frontmatter, and parses markdown and fenced executable blocks (`mdcc_chart`, `mdcc_table`) into a structured document model.
3. **Validator**: Performs structural validation of the parsed document, ensuring all block fences are closed and types are supported.
4. **Cache Resolver**: Computes execution and artifact fingerprints, validates dependency manifests for previously successful blocks, and decides whether a block can reuse a cached artifact, refresh an artifact from a cached semantic result, or must execute again.
5. **Executor**: Spawns isolated Python processes for cache misses, injects the fixed runtime prelude, captures stdout/stderr separately from the final expression evaluation, and records best-effort local file dependencies.
6. **Result Validator**: Validates the type of the final expression returned by execution blocks (e.g., Altair chart or pandas DataFrame).
7. **Artifact Renderers**: Converts validated execution results into document-ready static artifacts (HTML tables or static chart visuals). Cached semantic results can also be re-rendered here when the artifact fingerprint changes.
8. **Document Assembler**: Interleaves markdown narrative and rendered artifacts to generate an intermediate HTML document.
9. **PDF Generator**: Compiles the final assembled HTML document into the final PDF output.
10. **Diagnostics Engine**: Intercepts exceptions at any stage and formats them with file, location, and execution context for clear, actionable error reporting.

## Cache Model

Phase 1 caching is **per block** and **local to the source directory**.

- The persistent cache lives in `.mdcc_cache/` next to the source document.
- Each entry is keyed by an **execution fingerprint** that captures the block definition, runtime prelude fingerprint, `mdcc` version, Python version, and execution root.
- The execution fingerprint is currently **semantic rather than occurrence-specific**: it does not include the parsed block index, node id, or source span.
- As a result, two executable blocks in the same source directory with identical code, block type, runtime fingerprint, and execution root will resolve to the same cache entry. This includes duplicate blocks in the same document.
- Each entry also stores an **artifact fingerprint** so block-local rendered artifacts can be refreshed without re-executing the Python block when only rendering behavior changes.
- Cache validity additionally depends on the content hashes of tracked local filesystem reads discovered during execution.
- Final document assembly and PDF generation are always fresh; only block execution and block-local rendering are reused.

### Current Cache Tradeoff

The current design favors semantic cache reuse over per-occurrence isolation.

- Repeated identical blocks can reuse one cached semantic result and rendered artifact instead of executing independently.
- This improves reuse for documents that intentionally duplicate deterministic blocks.
- It also means the cache does **not** currently model block occurrence identity as a distinct input. Any future change that requires strict per-occurrence execution semantics would need an additional document/block identity layer in cache lookup.

## Directory Structure

The project uses a standard `src/` layout configured with `uv` and `pyproject.toml`.

```text
mdcc/
├── pyproject.toml             # Project config, dependencies, and uv configuration
├── README.md
├── docs/
│   ├── features/             # Technical specifications and feature designs
│   ├── TASKS.md               # Task Breakdown
│   └── ARCHITECTURE.md        # Architecture and Directory Structure (This file)
├── tests/                     # Test suite (pytest)
│   ├── conftest.py            # Test fixtures and shared test config
│   ├── test_cli.py            # CLI wiring tests
│   ├── test_reader.py         # Format/frontmatter extraction tests
│   ├── test_parser.py         # Markdown/block parsing tests
│   ├── test_validator.py      # Structural validation tests
│   ├── test_executor.py       # Isolated execution, timeout, and runtime tests
│   ├── test_renderers.py      # Chart and table artifact generation tests
│   └── test_e2e.py            # End-to-end PDF generation integration tests
└── src/
    └── mdcc/
        ├── __init__.py        # Package root and version
        ├── cache.py           # Persistent per-block cache store and fingerprinting
        ├── cli.py             # CLI entrypoints (Typer)
        ├── compile.py         # End-to-End Compiler Orchestrator
        ├── models.py          # Core domain data models (Pydantic v2)
        ├── errors.py          # Diagnostics model and typed exceptions
        ├── reader.py          # Source reader & frontmatter extraction
        ├── parser.py          # Markdown & Executable block parsing (Mistune)
        ├── validator.py       # Structural/Result validation logic
        ├── pdf.py             # Final PDF Generation (WeasyPrint)
        │
        ├── executor/          # Isolated Block Execution Module
        │   ├── __init__.py
        │   ├── runner.py      # subprocess orchestration and execution engine
        │   ├── payload.py     # block payload builder logic
        │   └── prelude.py     # fixed runtime environment injected into blocks, including dependency tracking
        │
        ├── renderers/         # Document and Artifact Rendering Module
        │   ├── __init__.py
        │   ├── chart.py       # Altair -> static image implementation
        │   ├── table.py       # pandas DataFrame -> HTML table implementation
        │   └── document.py    # narrative/artifact assembly (Jinja2)
        │
        └── utils/             # Helper utilities
            ├── __init__.py
            └── workspace.py   # Temporary build directory & asset management
```

## Technology Stack Mapping

- **CLI Shell**: `typer` (`src/mdcc/cli.py`)
- **Data Models**: `pydantic v2` (`src/mdcc/models.py`)
- **Markdown Parsing**: `mistune` (`src/mdcc/parser.py`)
- **Block Cache**: local JSON/file-based cache (`src/mdcc/cache.py`)
- **Isolated Execution**: `subprocess` standard library (`src/mdcc/executor/runner.py`)
- **Chart Rendering**: `altair` and `vl-convert-python` (`src/mdcc/renderers/chart.py`)
- **Table Rendering**: `pandas` built-in HTML styling (`src/mdcc/renderers/table.py`)
- **Document Rendering**: `Jinja2` (`src/mdcc/renderers/document.py`)
- **PDF Generation**: `WeasyPrint` (`src/mdcc/pdf.py`)

## Implementation Boundaries

1. **No Shared State**: Execution blocks explicitly cannot share globals or variables. They spawn fresh interpreters entirely on cache misses.
2. **Fresh Final Assembly**: Cache reuse stops at the block result / artifact boundary. Narrative assembly, reference resolution, and PDF generation are always recomputed for the current document.
3. **Best-Effort Dependency Tracking**: Phase 1 cache invalidation is guaranteed only for tracked local filesystem reads and runtime fingerprint changes. HTTP/network reads, time/randomness, environment variables, and other hidden ambient state are outside the cache guarantee.
   The current tracked read surface is intentionally narrow: `open(...)` plus the wrapped pandas readers `pd.read_csv`, `pd.read_json`, `pd.read_excel`, and `pd.read_parquet`. Other file access helpers, including `Path.read_text()`, `Path.read_bytes()`, and `Path.open()`, are not currently part of the cache invalidation contract.
4. **Data-Oriented Passing**: `models.py` remains the definitive contract between parser, validator, executor, renderer, and assembler stages.
