# mdcc — Software Architecture and Directory Structure

This document outlines the high-level architecture and directory structure for `mdcc` (Agent-First Executable Report Compiler), based on the requirements defined in the `SPEC.md` and `TASKS.md` documents.

## High-Level Architecture

The compiler acts as a linear, deterministic pipeline that transforms a single source text file containing markdown and executable blocks into a single PDF artifact. 

The pipeline is composed of the following core stages:

1. **CLI / Orchestrator**: The entrypoint that parses CLI arguments, orchestrates the compilation pipeline, and presents human-readable diagnostics.
2. **Reader & Parser**: Reads source files, extracts frontmatter, and parses markdown and fenced executable blocks (`mdcc_chart`, `mdcc_table`) into a structured document model.
3. **Validator**: Performs structural validation of the parsed document, ensuring all block fences are closed and types are supported.
4. **Executor**: Spawns isolated Python processes for each executable block sequentially, feeding them a fixed runtime prelude, capturing stdout/stderr separately from the final expression evaluation, and asserting timeout limits.
5. **Result Validator**: Validates the type of the final expression returned by execution blocks (e.g., Altair chart or pandas DataFrame).
6. **Artifact Renderers**: Converts validated execution results into document-ready static artifacts (HTML tables or static chart visuals).
7. **Document Assembler**: Interleaves markdown narrative and rendered artifacts to generate an intermediate HTML document.
8. **PDF Generator**: Compiles the final assembled HTML document into the final PDF output.
9. **Diagnostics Engine**: Intercepts exceptions at any stage and formats them with file, location, and execution context for clear, actionable error reporting.

## Directory Structure

The project uses a standard `src/` layout configured with `uv` and `pyproject.toml`.

```text
mdcc/
├── pyproject.toml             # Project config, dependencies, and uv configuration
├── README.md
├── docs/
│   ├── SPEC.md                # Project Specification
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
        ├── cli.py             # CLI entrypoints (Typer) [T06]
        ├── main.py            # End-to-End Compiler Orchestrator [T20]
        ├── models.py          # Core domain data models (Pydantic v2) [T02]
        ├── errors.py          # Diagnostics model and typed exceptions [T18, T19]
        ├── reader.py          # Source reader & frontmatter extraction [T03]
        ├── parser.py          # Markdown & Executable block parsing (Mistune) [T04]
        ├── validator.py       # Structural/Result validation logic [T05, T11]
        ├── pdf.py             # Final PDF Generation (WeasyPrint) [T17]
        │
        ├── executor/          # Isolated Block Execution Module [T07, T08, T09, T10]
        │   ├── __init__.py
        │   ├── runner.py      # subprocess orchestration and execution engine
        │   ├── payload.py     # block payload builder logic
        │   └── prelude.py     # fixed runtime environment injected into blocks
        │
        ├── renderers/         # Document and Artifact Rendering Module [T12, T13, T15, T16]
        │   ├── __init__.py
        │   ├── chart.py       # Altair -> static image implementation
        │   ├── table.py       # pandas DataFrame -> HTML table implementation
        │   └── document.py    # narrative/artifact assembly (Jinja2)
        │
        └── utils/             # Helper utilities [T14]
            ├── __init__.py
            └── workspace.py   # Temporary build directory & asset management
```

## Technology Stack Mapping

- **CLI Shell**: `typer` (`src/mdcc/cli.py`)
- **Data Models**: `pydantic v2` (`src/mdcc/models.py`)
- **Markdown Parsing**: `mistune` (`src/mdcc/parser.py`)
- **Isolated Execution**: `subprocess` standard library (`src/mdcc/executor/runner.py`)
- **Chart Rendering**: `altair` and `vl-convert-python` (`src/mdcc/renderers/chart.py`)
- **Table Rendering**: `pandas` built-in HTML styling (`src/mdcc/renderers/table.py`)
- **Document Rendering**: `Jinja2` (`src/mdcc/renderers/document.py`)
- **PDF Generation**: `WeasyPrint` (`src/mdcc/pdf.py`)

## Implementation Boundaries

1. **No Shared State**: Execution blocks in `executor/runner.py` explicitly cannot share globals or variables. They spawn fresh interpreters entirely.
2. **Data-Oriented Passing**: `models.py` acts as the definitive contract between stages. The `Parser` returns model instances, the `Executor` reads model instances and returns result models, and the `Renderer` consumes result models.
3. **No Stateful Pipelines**: The orchestrator in `main.py` simply coordinates the passing of `Pydantic` instances from one stateless module to the next, preventing tight coupling across compilation steps.
