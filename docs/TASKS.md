# TASKS.md

# mdcc — Implementation Task Breakdown

This document breaks the specification into implementation tasks that can be assigned to coding agents.

The goal is to make parallel work possible where reasonable, while keeping ownership boundaries clear.

This document intentionally:
- follows the spec
- does not introduce new product decisions
- does not prescribe implementation details beyond what is already defined
- does not resolve intentionally deferred questions from the spec

---

# 0. Task Tracking

Tasks are tracked using status markers in their headers.

- **(DONE)**: The task is fully implemented, scaffolds are created, and baseline functionality/tests for that unit are established.
- **(IN PROGRESS)**: A coding agent is currently working on this task.
- **(BLOCKED)**: The task is waiting on dependencies or a design decision.
- **(NO MARKER)**: The task is pending.

When a task is marked as **(DONE)**, it means downstream tasks can safely build upon its output or interfaces.

---

# 1. Task Breakdown Principles

## 1.1 Objectives
The task structure should:
- cover the full MVP scope from the specification
- separate concerns cleanly
- allow selected tasks to be implemented in parallel
- make dependencies explicit
- reduce merge conflicts between agents

## 1.2 Parallelization Strategy
Tasks are grouped into:
- **foundation tasks** — should begin first
- **parallelizable core tasks** — can be worked on concurrently once foundations are in place
- **integration tasks** — require outputs from multiple earlier tasks
- **hardening tasks** — testing, validation, and refinement

## 1.3 Ownership Guidance
Each task should ideally have:
- a clear scope
- a clear output
- minimal overlap with other tasks
- clear upstream dependencies

---

# 2. Task Overview

## T01 — Project Scaffold and Repository Baseline (DONE)
Create the baseline project structure for the CLI application and establish the initial repository layout needed for all later tasks.

### Scope
- set up the project as an MVP compiler codebase
- establish the package/module structure baseline
- create the initial entrypoint structure for future CLI work
- add baseline configuration files required by the chosen stack
- create placeholder locations for tests and implementation modules

### Output
A repository skeleton that other tasks can build on consistently.

### Dependencies
None.

### Parallelization
Must start first.

---

## T02 — Core Domain Models and Shared Types (DONE)
Define the shared internal models used across parsing, execution, rendering, diagnostics, and document assembly.

### Scope
- define document-level models
- define node/block models
- define frontmatter-related models
- define execution result models
- define validation result models
- define diagnostics-related structures
- define typed result categories for chart/table outputs

### Output
A stable shared model layer used by multiple other tasks.

### Dependencies
- T01

### Parallelization
Should start early. Many later tasks depend on it.

---

## T03 — Source Reader and Frontmatter Extraction (DONE)
Implement reading source files and extracting optional frontmatter from the document.

### Scope
- read the source file
- detect whether frontmatter is present
- separate frontmatter from markdown body
- validate supported frontmatter structure
- surface frontmatter-related errors
- produce normalized document input for downstream parsing

### Output
A frontmatter-aware document input stage.

### Dependencies
- T01
- T02

### Parallelization
Can run in parallel with some other early tasks.

---

## T04 — Markdown and Executable Block Parser (DONE)
Implement parsing of markdown narrative and fenced executable blocks into an internal document representation.

### Scope
- parse markdown content
- detect supported fenced executable block types
- preserve narrative ordering
- build narrative nodes and executable block nodes
- reject unsupported or malformed executable block forms
- preserve enough source location information for diagnostics

### Output
A parser that produces an internal representation of the source document.

### Dependencies
- T01
- T02
- T03

### Parallelization
Foundational core task.

---

## T05 — Structural Validation Layer (DONE)
Implement pre-execution validation of the parsed document.

### Scope
- validate that the document structure is supported
- validate that executable block types are known
- validate that block fences and parse results are structurally sound
- validate frontmatter presence/shape according to the spec
- produce clear structural validation failures

### Output
A validation stage that runs before execution begins.

### Dependencies
- T02
- T03
- T04

### Parallelization
Can proceed once parsing output shapes are available.

---

## T06 — CLI Surface and Command Wiring (DONE)
Implement the CLI entrypoints required to invoke the compiler.

### Scope
- define the top-level CLI command structure
- accept source and output paths
- connect the CLI to the compiler pipeline
- surface success and failure in CLI form
- ensure the CLI is consistent with the MVP compiler flow

### Output
A usable command-line interface for compilation.

### Dependencies
- T01

### Parallelization
Can begin early, but full usefulness depends on later integration tasks.

---

## T07 — Executable Block Payload Builder (DONE)
Implement the stage that converts parsed executable blocks into isolated execution payloads.

### Scope
- take executable block source and metadata from the parsed document
- prepare block-specific execution inputs
- incorporate fixed runtime assumptions from the spec
- prepare the data needed for isolated per-block execution
- preserve block identity and location for diagnostics

### Output
A payload/input representation for isolated block execution.

### Dependencies
- T02
- T04

### Parallelization
Can proceed in parallel with execution-runner work if interfaces are aligned.

---

## T08 — Isolated Block Execution Runner (DONE)
Implement isolated per-block execution in document order.

### Scope
- execute one block in its own Python process
- capture stdout and stderr
- enforce per-block timeout behavior
- report execution failures clearly
- support ordered execution across all executable blocks
- ensure no implicit shared runtime state exists between blocks

### Output
An execution runner for isolated chart/table blocks.

### Dependencies
- T02
- T07

### Parallelization
Core task. Can proceed in parallel with rendering and parsing tasks after interfaces are clear.

---

## T09 — Runtime Rule Enforcement (DONE)
Implement runtime-level checks required by the MVP execution model.

### Scope
- enforce the fixed runtime assumptions defined by the spec
- enforce the MVP rule around user imports
- classify violations as execution/validation failures as appropriate
- ensure executable blocks conform to the MVP runtime policy

### Output
Runtime-policy enforcement consistent with the specification.

### Dependencies
- T07
- T08

### Parallelization
Can be implemented alongside or immediately after the execution runner.

---

## T10 — Final Expression Capture and Typed Result Extraction (DONE)
Implement capture of the block’s final expression result and prepare it for typed validation.

### Scope
- capture the output defined by the block’s last expression
- associate the captured output with the corresponding executable block
- separate final value handling from stdout/stderr handling
- provide normalized result data for downstream validation

### Output
A typed-result extraction stage for executable blocks.

### Dependencies
- T02
- T08

### Parallelization
Can proceed in parallel with renderer tasks if contracts are synchronized.

---

## T11 — Typed Result Validator
Implement validation that block outputs match their required contracts.

### Scope
- validate `mdcc_chart` outputs against the chart contract
- validate `mdcc_table` outputs against the table contract
- reject invalid output types
- classify validation failures clearly
- preserve useful failure context for diagnostics

### Output
A result-validation stage that enforces semantic block contracts.

### Dependencies
- T02
- T10

### Parallelization
Can proceed in parallel with artifact renderers.

---

## T12 — Chart Artifact Renderer (DONE)
Implement rendering of validated chart results into document-ready artifacts.

### Scope
- accept validated chart outputs
- turn them into renderable chart artifacts for document assembly
- preserve block association for placement in the final document
- surface rendering failures clearly

### Output
A chart rendering stage that produces document-ready chart artifacts.

### Dependencies
- T11

### Parallelization
Can proceed in parallel with T13 once typed result contracts are stable.

---

## T13 — Table Artifact Renderer (DONE)
Implement rendering of validated table results into document-ready artifacts.

### Scope
- accept validated table outputs
- turn them into renderable table artifacts for document assembly
- preserve block association for placement in the final document
- surface rendering failures clearly

### Output
A table rendering stage that produces document-ready table artifacts.

### Dependencies
- T11

### Parallelization
Can proceed in parallel with T12.

---

## T14 — Temporary Build Artifact Management (DONE)
Implement management of intermediate build assets used during compilation.

### Scope
- create and manage the temporary build directory
- define the lifecycle of intermediate artifacts during a compilation run
- support temporary assets created by execution/rendering steps
- preserve or clean artifacts according to the eventual compiler behavior

### Output
A build-artifact management layer for intermediate compiler outputs.

### Dependencies
- T01

### Parallelization
Can begin relatively early and be integrated by several later tasks.

---

## T15 — Narrative Rendering and Document Assembly Model (DONE)
Implement the stage that combines markdown narrative with rendered executable-block artifacts into a unified final document representation.

### Scope
- preserve original document order
- interleave narrative content with rendered chart/table artifacts
- define the assembled document representation used by the final rendering stage
- ensure executable outputs appear in the correct positions relative to markdown narrative

### Output
A final document assembly representation ready for PDF generation.

### Dependencies
- T04
- T12
- T13

### Parallelization
Begins after renderers are available.

---

## T16 — Intermediate Document Rendering (DONE)
Implement rendering of the assembled document into the intermediate representation used before PDF generation.

### Scope
- transform the assembled document representation into the pre-PDF document form
- include rendered narrative and executable artifacts in correct order
- support document-level metadata insertion where applicable
- surface rendering-stage failures clearly

### Output
An intermediate rendered document ready for PDF generation.

### Dependencies
- T15

### Parallelization
Depends on assembly output.

---

## T17 — PDF Generation Stage (DONE)
Implement the final PDF production step.

### Scope
- accept the intermediate rendered document
- generate the final PDF output file
- classify and report PDF-generation failures
- ensure successful compilation produces exactly one final PDF artifact

### Output
A working PDF output stage for the compiler.

### Dependencies
- T16

### Parallelization
Mostly downstream; limited independent work before integration.

---

## T18 — Diagnostics Model and Error Classification (DONE)
Implement the diagnostics layer used across parse, validation, execution, rendering, timeout, and PDF-generation failures.

### Scope
- define failure categories from the spec
- ensure failures can carry file/block/stage context
- support human-readable diagnostic output needs
- preserve room for future structured agent-oriented diagnostics
- ensure error reporting is consistent across the pipeline

### Output
A unified diagnostics framework for compiler errors.

### Dependencies
- T02

### Parallelization
Should start early. Multiple other tasks will use it.

---

## T19 — Human-Readable Diagnostic Reporting (DONE)
Implement compiler-facing diagnostic presentation for human users.

### Scope
- present clear failures at the CLI/compiler output boundary
- include file path, block type, location, stage, and error message where available
- present concise source references or snippets where appropriate
- ensure failures remain understandable without reading internal traces

### Output
Human-readable compiler diagnostics aligned with the spec.

### Dependencies
- T06
- T18
- partial integrations from parser/execution/rendering tasks

### Parallelization
Can be developed in parallel once diagnostics structures exist.

---

## T20 — End-to-End Compiler Orchestrator
Implement the top-level compiler flow that connects all stages.

### Scope
- orchestrate reading, parsing, validation, execution, rendering, assembly, and PDF generation
- preserve deterministic top-to-bottom execution order
- stop appropriately on failure
- route diagnostics through the reporting layer
- produce the final compile success/failure result

### Output
A full compilation pipeline from input document to final PDF.

### Dependencies
- T03 through T19 as applicable

### Parallelization
Integration task. Must be done after enough core components exist.

---

## T21 — Frontmatter and Metadata Behavior Tests (DONE)
Create tests that cover supported frontmatter behavior and document-level metadata handling.

### Scope
- valid frontmatter cases
- missing frontmatter cases
- invalid frontmatter cases
- supported field handling
- stable handling of unsupported or unknown fields according to chosen implementation behavior

### Output
Test coverage for frontmatter behavior.

### Dependencies
- T03
- T05

### Parallelization
Can be done alongside other testing tasks.

---

## T22 — Parsing and Structural Validation Tests (DONE)
Create tests for markdown parsing, executable block parsing, and structural validation.

### Scope
- valid document parsing
- supported executable block recognition
- malformed fenced block failures
- unsupported block type failures
- mixed narrative/block ordering cases
- source location preservation where applicable

### Output
Test coverage for parser and structural validator behavior.

### Dependencies
- T04
- T05

### Parallelization
Can proceed in parallel with other test tracks.

---

## T23 — Execution and Runtime Policy Tests (DONE)
Create tests for isolated execution behavior and runtime-rule enforcement.

### Scope
- block execution success cases
- no shared state across blocks
- stdout/stderr capture cases
- timeout behavior
- user import policy behavior
- deterministic ordered execution behavior

### Output
Test coverage for execution behavior.

### Dependencies
- T08
- T09
- T10

### Parallelization
Parallelizable with renderer and diagnostics tests.

---

## T24 — Typed Result Validation Tests (DONE)
Create tests for semantic output contract enforcement.

### Scope
- valid chart block outputs
- invalid chart block outputs
- valid table block outputs
- invalid table block outputs
- `None` or unsupported last-expression results
- correct failure classification for contract violations

### Output
Test coverage for result contract validation.

### Dependencies
- T11

### Parallelization
Can proceed in parallel with renderer tests.

---

## T25 — Artifact Rendering Tests (DONE)
Create tests for chart and table artifact rendering.

### Scope
- successful chart artifact generation
- successful table artifact generation
- failures in rendering pipeline
- stable association of rendered artifacts with source blocks

### Output
Test coverage for rendering stages.

### Dependencies
- T12
- T13

### Parallelization
Can run in parallel with other testing tracks.

---

## T26 — PDF Generation and End-to-End Golden Path Tests
Create tests for full document compilation through to PDF output.

### Scope
- golden-path compile success for representative documents
- documents containing narrative + chart + table blocks
- compile failure propagation in downstream stages
- final PDF output existence and expected behavior at a high level

### Output
End-to-end test coverage for the MVP compiler.

### Dependencies
- T17
- T20

### Parallelization
Primarily later-stage testing.

---

## T27 — Diagnostics and Failure-Mode Tests (DONE)
Create tests covering failure classification and reporting.

### Scope
- parse errors
- execution errors
- timeout errors
- validation errors
- rendering errors
- PDF generation errors
- human-readable diagnostics content expectations

### Output
Test coverage for diagnostic quality and consistency.

### Dependencies
- T18
- T19
- relevant producing tasks

### Parallelization
Can be developed progressively.

---

## T28 — Documentation for Supported Source Format
Write the initial implementation-facing documentation for the supported source format.

### Scope
- describe supported document structure
- describe frontmatter usage
- describe supported executable block types
- describe last-expression output rules
- describe what is out of scope in MVP
- describe how stdout/stderr differ from rendered output

### Output
A documentation page for the source format as implemented.

### Dependencies
- T04
- T11
- T15

### Parallelization
Can begin once core behavior is stable.

---

## T29 — Documentation for Compiler Usage and Failure Interpretation
Write user/developer-facing documentation for invoking the compiler and understanding failures.

### Scope
- describe how to run compilation
- describe high-level compiler stages
- describe common failure categories
- describe how executable block failures should be interpreted
- describe temporary build artifact behavior if exposed

### Output
A usage and troubleshooting documentation page.

### Dependencies
- T06
- T19
- T20

### Parallelization
Can proceed once compiler integration exists.

---

# 3. Suggested Parallel Work Packages

The following grouping is one reasonable way to divide work among agents.

## Work Package A — Core Document Ingestion
Includes:
- T03 — Source Reader and Frontmatter Extraction
- T04 — Markdown and Executable Block Parser
- T05 — Structural Validation Layer
- T22 — Parsing and Structural Validation Tests
- T21 — Frontmatter and Metadata Behavior Tests

### Notes
This package owns getting from source text to a validated internal document representation.

---

## Work Package B — Execution Core
Includes:
- T07 — Executable Block Payload Builder
- T08 — Isolated Block Execution Runner
- T09 — Runtime Rule Enforcement
- T10 — Final Expression Capture and Typed Result Extraction
- T23 — Execution and Runtime Policy Tests

### Notes
This package owns isolated execution behavior and raw execution results.

---

## Work Package C — Semantic Validation and Renderers
Includes:
- T11 — Typed Result Validator
- T12 — Chart Artifact Renderer
- T13 — Table Artifact Renderer
- T24 — Typed Result Validation Tests
- T25 — Artifact Rendering Tests

### Notes
This package owns semantic output enforcement and rendering of executable results.

---

## Work Package D — Assembly and Final Output
Includes:
- T15 — Narrative Rendering and Document Assembly Model
- T16 — Intermediate Document Rendering
- T17 — PDF Generation Stage
- T26 — PDF Generation and End-to-End Golden Path Tests

### Notes
This package owns the final document build path.

---

## Work Package E — Diagnostics and Compiler Interface
Includes:
- T06 — CLI Surface and Command Wiring
- T18 — Diagnostics Model and Error Classification
- T19 — Human-Readable Diagnostic Reporting
- T27 — Diagnostics and Failure-Mode Tests

### Notes
This package owns how the compiler is invoked and how failures are surfaced.

---

## Work Package F — Integration and Documentation
Includes:
- T14 — Temporary Build Artifact Management
- T20 — End-to-End Compiler Orchestrator
- T28 — Documentation for Supported Source Format
- T29 — Documentation for Compiler Usage and Failure Interpretation

### Notes
This package integrates the compiler and documents the implemented behavior.

---

# 4. Dependency Summary

## Earliest-start tasks
- T01 — Project Scaffold and Repository Baseline
- T02 — Core Domain Models and Shared Types
- T06 — CLI Surface and Command Wiring
- T14 — Temporary Build Artifact Management
- T18 — Diagnostics Model and Error Classification

## Foundational pipeline tasks
- T03 — Source Reader and Frontmatter Extraction
- T04 — Markdown and Executable Block Parser
- T05 — Structural Validation Layer
- T07 — Executable Block Payload Builder
- T08 — Isolated Block Execution Runner

## Mid-pipeline tasks
- T09 — Runtime Rule Enforcement
- T10 — Final Expression Capture and Typed Result Extraction
- T11 — Typed Result Validator
- T12 — Chart Artifact Renderer
- T13 — Table Artifact Renderer
- T15 — Narrative Rendering and Document Assembly Model

## Downstream integration tasks
- T16 — Intermediate Document Rendering
- T17 — PDF Generation Stage
- T19 — Human-Readable Diagnostic Reporting
- T20 — End-to-End Compiler Orchestrator

## Final validation tasks
- T21 through T29

---

# 5. Minimal Sequencing Recommendation

A minimal implementation sequence could be:

1. T01
2. T02, T06, T14, T18
3. T03, T04, T05
4. T07, T08, T09, T10
5. T11, T12, T13
6. T15, T16, T17
7. T19, T20
8. T21–T29

This sequence is guidance only.

---

# 6. Task Completion Standard

A task should be considered complete when:
- its scope is implemented
- its outputs match the spec section(s) it covers
- relevant tests exist or are updated
- it does not introduce product decisions outside the spec
- it integrates cleanly with upstream/downstream tasks

---

# 7. Final Note

This task breakdown is intentionally product-neutral beyond the given specification.
It is designed to help coding agents work in parallel without redefining the compiler.

Where the specification defers a decision, the corresponding task should preserve that deferral rather than silently resolving it.
