# Agent-First Executable Report Compiler — Technical Specification

## Status
Draft MVP specification for implementation.

## Purpose
Define a minimal, deterministic, agent-friendly document compiler that turns a single source file containing markdown narrative and executable analysis blocks into a PDF.

This document is written as an implementation spec, not a product PRD.

---

# 1. Product Summary

The tool compiles a **single plain-text source file** into a **single PDF output**.

The source document contains:
- frontmatter
- normal markdown narrative
- executable chart blocks
- executable table blocks

The tool is intentionally narrow and opinionated:
- markdown with powers, not a notebook
- Python-only execution for MVP
- fixed built-in runtime
- no user imports in executable blocks
- isolated execution per block
- deterministic document order execution
- PDF-only output for MVP
- strong diagnostics for humans and coding agents

The tool is designed primarily for:
- technical analysis memos
- small research papers
- internal strategy notes
- reproducible analysis reports
- agent-generated or agent-maintained analytical documents

---

# 2. Core Principles

## 2.1 Single-file source of truth
Everything needed to define the report lives in one text file:
- narrative
- executable logic
- chart/table definitions
- document metadata

No notebook JSON, hidden UI state, or manual copy-paste workflow.

## 2.2 Plain text and git-friendly
The source format must remain easy to diff, edit, merge, and modify with existing coding-agent harnesses.

## 2.3 Deterministic execution
Given the same source file and the same external inputs, the compiler should produce the same output.

## 2.4 No implicit shared runtime state
Executable blocks must not share variables or runtime objects implicitly.
Each block is an isolated execution unit.

## 2.5 Agent-first ergonomics
The format, runtime model, and diagnostics must be easy for coding agents to:
- generate
- edit
- reason about
- debug
- rerun

## 2.6 Opinionated MVP
The tool should be intentionally narrower than Quarto or notebooks.
This is a focused compiler for agent-friendly analytical reports, not a general publishing system.

---

# 3. Goals

## 3.1 MVP goals
- Compile one source file into one PDF.
- Support markdown narrative.
- Support semantic executable blocks for charts and tables.
- Run each block in isolation.
- Validate typed outputs from each block.
- Render chart/table results into the final document.
- Provide clear compiler errors.
- Fit naturally into existing agent workflows that edit files and run shell commands.

## 3.2 Design goals
- low syntax overhead
- low ambiguity
- easy static inspection
- predictable behavior
- clean implementation path
- room for future extension without compromising clarity

---

# 4. Non-goals (MVP)

The following are explicitly out of scope for MVP:
- notebook compatibility
- HTML, Word, slide, or website output
- interactive charts/widgets
- multi-file projects
- shared runtime state across blocks
- imports written by users inside executable blocks
- arbitrary Python package access beyond the fixed runtime
- user-defined custom block types
- generic compute blocks
- image embed blocks
- includes/imports from external source files
- arbitrary language support besides Python
- layout-heavy publishing features
- collaboration features
- scheduling/CI features
- caching implementation
- agent-specific protocol beyond normal file editing and CLI execution

Future versions may add some of these features, but the MVP must not depend on them.

---

# 5. Supported Document Model

## 5.1 High-level structure
A document contains, in order:
1. optional frontmatter
2. markdown narrative
3. executable blocks interleaved with markdown

## 5.2 Supported content types (MVP)
- frontmatter
- markdown text
- `mdcc_chart` block
- `mdcc_table` block

## 5.3 Deferred content types
Explicitly deferred:
- image/embed blocks
- generic compute blocks
- imported code blocks
- external helper files
- inline reusable definitions

---

# 6. Frontmatter

## 6.1 Purpose
Frontmatter stores document-level metadata.

## 6.2 MVP expectation
Frontmatter is allowed, but the MVP should keep supported fields minimal.

Recommended initial fields:
- `title`
- `author`
- `date`

Optional implementation detail:
- unknown frontmatter fields may either be ignored or preserved for future use
- behavior should be documented and stable

## 6.3 Example shape
YAML-style frontmatter at the top of the file is recommended.

The exact syntax should stay markdown-adjacent and familiar.

---

# 7. Executable Block Types

## 7.1 Overview
Two semantic executable block types are supported in MVP:
- `mdcc_chart`
- `mdcc_table`

Each block is self-contained.
Each block runs independently.
Each block has a typed return contract.

## 7.2 Why semantic blocks
Semantic block types are preferred over generic code blocks because they are:
- easier for agents to generate correctly
- easier to validate statically and dynamically
- easier to render deterministically
- easier to debug
- easier to extend later with richer diagnostics

---

# 8. Block Syntax

## 8.1 Syntax philosophy
The syntax should feel like markdown with powers.
It should reuse familiar fenced-block conventions rather than inventing a new document language.

## 8.2 MVP syntax requirement
Blocks must be fenced and clearly typed.

Conceptually:
- a chart block is a fenced block tagged as `mdcc_chart`
- a table block is a fenced block tagged as `mdcc_table`

## 8.3 Metadata
Block-level metadata is intentionally omitted in MVP.
Possible future metadata may include:
- caption
- label
- width
- placement hints

The current syntax should leave room to add metadata later without breaking the core model.

---

# 9. Execution Model

## 9.1 Execution order
Executable blocks run **top to bottom in document order**.

This order is deterministic and stable.

## 9.2 Isolation model
Each executable block runs in its **own Python process**.

This is a deliberate MVP decision.

### Rationale
- strong isolation
- fewer hidden state problems
- easier debugging
- easier future caching model
- easier future sandboxing
- easier reasoning for agents

## 9.3 No implicit state sharing
Variables, functions, imports, and runtime objects created in one block must not be visible to another block.

There is no shared notebook-style state.

## 9.4 Process lifecycle
For each executable block, the compiler should:
1. create an isolated execution payload
2. start a fresh Python process
3. inject the fixed runtime prelude
4. execute the block code
5. capture stdout/stderr and final expression result
6. validate the result against the block type contract
7. render the result into a document artifact
8. terminate the process

## 9.5 Timeout
Each executable block should have a timeout.

Exact timeout value may be configurable later, but MVP should define a sensible default.
A recommended default is in the range of 30 to 60 seconds.

If a block exceeds the timeout, compilation fails with a clear timeout error.

---

# 10. Runtime Environment

## 10.1 Language
Python only for MVP.

## 10.2 Fixed built-in environment
The runtime environment is fixed and provided by the compiler.
Users do not need to import supported libraries.

## 10.3 User imports
User-written imports inside executable blocks are **not allowed in MVP**.

### Rationale
- tighter control over environment
- lower complexity
- more predictable code generation by agents
- easier diagnostics
- easier security and implementation discipline

## 10.4 Built-in libraries
The built-in environment should include:
- `pandas` as `pd`
- `numpy` as `np`
- chart library object(s) required for chart blocks

## 10.5 Runtime documentation
The fixed runtime prelude must be clearly documented in the implementation and user-facing docs.
The environment must not be magical or ambiguous.

---

# 11. Chart Library Choice

## 11.1 Selected chart library
Use **Altair** for MVP charts.

## 11.2 Rationale
Altair is preferred because it is:
- declarative
- cleanly object-based
- more predictable for agents
- easier to validate than imperative plotting flows
- suitable for standard analytical charts

## 11.3 Scope
Only Altair chart objects are accepted by `mdcc_chart` blocks in MVP.

Matplotlib, Seaborn, and Plotly are out of scope for MVP.

---

# 12. Table Representation Choice

## 12.1 Selected table return type
Use **pandas DataFrame** as the required result type for `mdcc_table` blocks.

## 12.2 Rationale
A DataFrame is:
- a standard analysis object
- easy for agents to produce
- easy to validate
- easy to render into a document table

---

# 13. Output Contracts

## 13.1 General rule
The **last expression** in an executable block is the block’s output.

The compiler captures and validates that final value.

This output is returned to the compiler runtime, not to other blocks.

## 13.2 Why last-expression semantics
This design is preferred because it is:
- concise
- familiar
- low ceremony
- easy for agents
- easier than explicit render calls for MVP

## 13.3 `mdcc_chart` contract
A `mdcc_chart` block must evaluate to an **Altair chart object** as its last expression.

If the final value is not a supported chart object, compilation fails.

## 13.4 `mdcc_table` contract
A `mdcc_table` block must evaluate to a **pandas DataFrame** as its last expression.

If the final value is not a DataFrame, compilation fails.

## 13.5 No implicit render helpers required
MVP should not require special user calls like:
- `render_chart(...)`
- `emit_table(...)`
- explicit output channels

The last expression is enough.

## 13.6 Wrong-type failures
Examples of compile failures:
- chart block returns DataFrame
- table block returns scalar
- final value is `None`
- output object cannot be rendered

---

# 14. Logging and Print Behavior

## 14.1 `print()` is allowed
`print()` and normal stdout are allowed for debugging.

## 14.2 Printed output is not rendered
Printed output does **not** become part of the document.

It belongs only to execution logs and traces.

## 14.3 Separation of concerns
- final expression -> document output
- stdout/stderr -> diagnostics only

This distinction is critical and must remain clear.

---

# 15. Rendering Model

## 15.1 Overview
Executable blocks do not directly write PDF content.
They produce typed results that the compiler renders into document artifacts.

## 15.2 Rendering pipeline
Conceptually:
- block source
- block execution
- typed result capture
- result validation
- result rendering
- artifact insertion into document

## 15.3 Chart rendering
For `mdcc_chart` blocks:
1. execute block
2. capture final value
3. validate Altair chart object
4. render chart to a static visual artifact
5. insert artifact into document

In the final PDF, chart blocks appear as rendered chart visuals.

### Artifact form
The implementation may use a static image or vector representation internally.
The PDF consumer only sees the rendered chart artifact.

## 15.4 Table rendering
For `mdcc_table` blocks:
1. execute block
2. capture final value
3. validate DataFrame
4. render DataFrame into a presentable table representation
5. insert table artifact into document

The implementation may use an internal HTML rendering step if useful.

## 15.5 User mental model
Authors think in terms of returning chart and table objects.
They do not think in terms of manually creating images or layout fragments.

---

# 16. Temporary Build Artifacts

## 16.1 Build directory
The compiler should use a temporary build directory for intermediate assets.

Recommended convention:
- a hidden build folder adjacent to the source or in a predictable temporary path
- example placeholder: `.mdcc_build/`

The exact folder name may change but will follow the tool name convention.

## 16.2 Contents
The build directory may contain:
- rendered chart assets
- intermediate rendered tables
- execution payloads
- logs/traces
- temporary layout artifacts

## 16.3 Lifecycle
MVP may either:
- keep the build directory for inspection
- or clean it automatically on success

Behavior should be explicit and documented.

---

# 17. PDF Output

## 17.1 Only supported output format
PDF only for MVP.

## 17.2 Input-output promise
The user provides one source file.
The compiler produces one PDF file.

No other official outputs are required in MVP.

## 17.3 Internal rendering freedom
The implementation may use intermediate representations internally, such as HTML, but those are not part of the public product contract.

---

# 18. Diagnostics and Error Model

## 18.1 Importance
Diagnostics are a first-class product feature.
This tool is explicitly designed for coding-agent workflows, so errors must be useful for both humans and agents.

## 18.2 Minimum human-readable diagnostics
On failure, the compiler should provide:
- file path
- block type
- block location (line range if possible)
- concise source snippet or reference
- error class/category
- error message
- whether the failure occurred during parse, execution, validation, rendering, or timeout

## 18.3 Desired structure of failures
Failures should be categorized, at minimum, into:
- parse error
- block execution error
- timeout error
- validation error
- rendering error
- PDF generation error

## 18.4 Agent-friendly trace mode
Structured diagnostics for agents are highly desirable.
This may be implemented later, but the architecture should allow it.

Possible structured fields:
- file
- block index
- block type
- line range
- stage
- duration_ms
- stdout
- stderr
- exception_type
- exception_message
- stack_trace
- expected_output_type
- actual_output_type

## 18.5 Variable capture philosophy
Do **not** dump every variable blindly by default.
That creates too much noise.

Instead, future diagnostics may capture **summaries** of locals on failure, for example:
- variable names
- variable types
- DataFrame shapes
- column names
- truncated previews
- scalar values

The default philosophy is: capture useful summaries, not everything.

---

# 19. Parsing and Validation

## 19.1 Parsing stages
The compiler should conceptually perform:
1. source read
2. frontmatter parse
3. markdown/block parse
4. structural validation
5. executable block extraction
6. execution and rendering
7. final document assembly
8. PDF generation

## 19.2 Structural validation
Before execution, the compiler should validate:
- document is syntactically well-formed
- block fences are closed
- block types are supported
- frontmatter is valid if present

## 19.3 Block validation
Before or after execution, the compiler should validate:
- block type is known
- block output matches expected type
- renderable artifact can be generated

---

# 20. Caching Considerations (Design Only)

Caching is out of scope for MVP implementation, but the architecture should not block it later.

## 20.1 Future-friendly design goal
Each executable block should be independently hashable based on things like:
- block source content
- runtime version
- compiler version
- relevant document options

## 20.2 Implication
The isolated-block model is intentionally compatible with future per-block caching.

No caching behavior is required in MVP.

---

# 21. Extensibility Guidelines

## 21.1 Future additions that should remain possible
- image/embed blocks
- generic compute blocks
- explicit reusable code modules
- imports/includes
- block metadata
- agent-oriented structured error output
- per-block caching
- additional output formats

## 21.2 Constraint on future evolution
Future extensions must not break the core principle:
**no implicit shared runtime state between executable blocks**.

Explicit reuse is acceptable in future versions.
Implicit leakage is not.

---

# 22. Open Questions Deferred Intentionally

The following are intentionally deferred and should not block MVP implementation:
- exact CLI command shape
- exact default timeout value
- exact structured error format schema
- exact temporary build folder name
- exact PDF rendering stack
- exact frontmatter field policy for unknown keys
- whether build artifacts are preserved or cleaned by default

These should be documented as implementation notes, not treated as blockers.

---

# 23. Recommended Internal Compiler Stages

A clean internal architecture may follow this structure:

1. **Reader**
   - load source text

2. **Parser**
   - parse frontmatter
   - parse markdown and fenced executable blocks

3. **Document Model Builder**
   - build internal representation of narrative nodes and executable block nodes

4. **Validator**
   - validate structure and supported block types

5. **Executor**
   - run each block in isolated Python process
   - capture stdout/stderr/final value
   - enforce timeout

6. **Typed Result Validator**
   - confirm block result matches expected contract

7. **Renderer**
   - render chart/table results into document artifacts

8. **Assembler**
   - merge narrative and rendered artifacts into a final document representation

9. **PDF Generator**
   - produce final PDF

10. **Diagnostics Reporter**
   - surface clear failure messages and optional structured traces

This section is guidance, not a mandatory package/module structure.

---

# 24. Example Semantic Rules Summary

## `mdcc_chart`
- runs in isolated Python process
- no user imports allowed
- fixed runtime prelude available
- last expression must be Altair chart
- stdout/stderr go to logs only
- rendered output becomes chart artifact embedded in PDF

## `mdcc_table`
- runs in isolated Python process
- no user imports allowed
- fixed runtime prelude available
- last expression must be pandas DataFrame
- stdout/stderr go to logs only
- rendered output becomes table artifact embedded in PDF

---

# 25. Final MVP Definition

The MVP is complete when the tool can:
- read one markdown-like source file with frontmatter, narrative, and typed executable blocks
- execute chart/table blocks independently in isolated Python processes
- validate their outputs
- render them into a final document
- emit one PDF
- fail with clear, useful diagnostics

It is **not** necessary for MVP to support:
- fancy publishing features
- notebooks
- multiple output formats
- cross-block computation
- general-purpose extensibility

The product should win by being:
- smaller
- clearer
- more deterministic
- more agent-friendly
than broader existing tools.

---

# 26. Implementation Bias

When implementation tradeoffs appear, prefer:
- simplicity over flexibility
- explicitness over magic
- determinism over convenience
- typed contracts over permissive behavior
- good diagnostics over clever shortcuts
- narrow scope over premature extensibility

This bias is part of the product definition.

---


# 27. Implementation Technology Stack (MVP)

The compiler should be implemented as a **Python CLI application**.
The technology stack prioritizes **simplicity, determinism, and fast implementation**.

## Core Language

* **Python 3.12+**

## Project Management

* **uv** for dependency and environment management
* **pyproject.toml** for project configuration

## CLI

* **Typer** for command-line interface

Example command:

```
report compile input.md output.pdf
```

## Markdown Parsing

* **Mistune** for parsing markdown and detecting fenced executable blocks

## Data Models

* **Pydantic v2** for:

  * frontmatter validation
  * document node models
  * execution result validation
  * diagnostic structures

## Block Execution

* **subprocess (Python stdlib)**

Each executable block runs in an **isolated Python process** with a fixed runtime environment.

## Runtime Libraries

Available automatically in execution blocks:

* **pandas** (`pd`)
* **numpy** (`np`)
* **Altair**

User imports are not allowed in MVP.

## Chart Rendering

* **Altair + vl-convert-python** for generating static chart images

## Table Rendering

* **pandas DataFrame → HTML table**

## Document Rendering

* **Jinja2** for generating an intermediate HTML document

## PDF Generation

* **WeasyPrint** for HTML → PDF conversion

## Testing

* **pytest**

## Development Tooling

* **ruff**
* **mypy** (optional)

## Stack Summary

```
Python 3.12
uv
Typer
Mistune
Pydantic v2
subprocess
pandas
numpy
Altair
vl-convert-python
Jinja2
WeasyPrint
pytest
```
