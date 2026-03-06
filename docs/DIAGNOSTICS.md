# Diagnostics and Error Handling

This document describes the current diagnostics and error-handling framework used by `mdcc`.

It reflects the implementation in:

- `src/mdcc/models.py`
- `src/mdcc/errors.py`
- `src/mdcc/reader.py`
- `src/mdcc/parser.py`
- `src/mdcc/validator.py`

The goal of the framework is to provide:

- stable error categories across compiler stages
- structured error payloads for machines and agents
- enough context for human-readable reporting
- a consistent way for pipeline stages to raise failures

## Overview

The diagnostics layer is built from two pieces:

1. `Diagnostic` in `src/mdcc/models.py`
2. `MdccError` and its subclasses in `src/mdcc/errors.py`

The pattern is:

- a stage detects a failure
- it creates a typed compiler error using `*.from_message(...)` or `*.from_exception(...)`
- that error wraps a `Diagnostic`
- higher layers can inspect `error.diagnostic` or render a human-facing message later

## Core Diagnostic Model

The `Diagnostic` model is the canonical structured error payload.

Current fields:

- `stage`: pipeline stage where the error occurred
- `category`: error class within the stage
- `message`: short human-readable summary
- `source_path`: source file path if known
- `block_id`: executable block identifier if known
- `block_type`: semantic block type if known
- `block_index`: zero-based executable block index if known
- `location`: source location object if known
- `source_snippet`: short relevant source excerpt
- `stdout`: captured standard output, primarily for execution-stage failures
- `stderr`: captured standard error, primarily for execution-stage failures
- `exception_type`: underlying Python exception type if one exists
- `exception_message`: underlying exception text or aggregated issue summary
- `stack_trace`: reserved for richer future traces
- `expected_output_type`: expected semantic/runtime type
- `actual_output_type`: actual semantic/runtime type
- `duration_ms`: stage or block duration when applicable

## DiagnosticStage

`DiagnosticStage` defines where a failure happened:

- `read`
- `parse`
- `validation`
- `execution`
- `timeout`
- `rendering`
- `pdf`

These values are intentionally stable because later CLI/reporting layers will branch on them.

## DiagnosticCategory

`DiagnosticCategory` defines the broad failure class:

- `read_error`
- `parse_error`
- `validation_error`
- `execution_error`
- `timeout_error`
- `rendering_error`
- `pdf_error`

For the current implementation, the category generally maps one-to-one with the typed exception class.

## Source Context

Source-aware diagnostics use the following supporting models:

- `SourcePosition`
- `SourceSpan`
- `SourceLocation`

These live in `src/mdcc/models.py`.

Typical usage:

- reader errors attach file-level context
- parser errors attach line ranges and fence snippets
- validation errors attach the location of the invalid node when available

## Typed Exception Classes

All compiler exceptions inherit from `MdccError`.

Current subclasses:

- `ReadError`
- `ParseError`
- `ValidationError`
- `ExecutionError`
- `TimeoutError`
- `RenderingError`
- `PdfGenerationError`

Each subclass defines:

- a default `DiagnosticStage`
- a default `DiagnosticCategory`

That means callers usually do not need to repeat the stage/category manually.

## ErrorContext

`ErrorContext` is a small reusable container for shared diagnostic fields:

- `source_path`
- `block_id`
- `block_type`
- `block_index`
- `location`

Use it when a stage already knows the relevant document/block context and wants to avoid repeatedly passing the same fields into every error factory call.

Example:

```python
from mdcc.errors import ErrorContext, ParseError

context = ErrorContext(source_path=path, location=location)
raise ParseError.from_message("unsupported block", context=context)
```

## Factory APIs

### `from_message(...)`

Use this when there is no underlying Python exception to preserve.

Example:

```python
raise ValidationError.from_message(
    "frontmatter must be a YAML mapping",
    context=ErrorContext(source_path=path),
    expected_output_type="dict",
    actual_output_type=type(payload).__name__,
)
```

### `from_exception(...)`

Use this when wrapping an existing exception.

This automatically captures:

- `exception_type`
- `exception_message`

Example:

```python
try:
    payload = yaml.safe_load(frontmatter_text)
except yaml.YAMLError as exc:
    raise ParseError.from_exception(
        "frontmatter contains invalid YAML",
        exc,
        context=ErrorContext(source_path=path, location=location),
    ) from exc
```

## DiagnosticCollector

`DiagnosticCollector` accumulates multiple diagnostics before raising a single typed error.

This is useful for stages that can discover several issues in one pass, such as structural validation.

Current behavior:

- `add(...)` appends one `Diagnostic`
- `extend(...)` appends many diagnostics
- `diagnostics` returns a copy of the current list
- `has_errors()` reports whether anything has been collected
- `raise_if_any(...)` raises a typed `MdccError` subclass using the first diagnostic as the primary context and joins all messages into `exception_message`

Example:

```python
collector = DiagnosticCollector()
collector.add(diagnostic_a)
collector.add(diagnostic_b)
collector.raise_if_any(ValidationError, message="document validation failed")
```

## Current Stage Usage

### Reader

`src/mdcc/reader.py` uses:

- `ReadError.from_exception(...)` for file I/O and decode failures
- `ParseError.from_message(...)` for unclosed frontmatter delimiters
- `ParseError.from_exception(...)` for invalid YAML syntax
- `ValidationError.from_message(...)` for valid YAML with unsupported shape
- `ValidationError.from_exception(...)` for frontmatter model validation failures

### Parser

`src/mdcc/parser.py` uses:

- `ParseError.from_message(...)` for unsupported `mdcc_*` fences
- `ParseError.from_message(...)` for unclosed executable fences

Parser diagnostics currently include:

- source path
- line-based location
- short source snippet

### Validator

`src/mdcc/validator.py` uses:

- `ValidationResult[DocumentModel]` for non-raising validation
- `ValidationError.from_message(...)` when the caller wants a raised failure

The validator currently aggregates issue summaries into `exception_message`.

## Compatibility Notes

The framework is currently compatible with the implemented stages:

- reader
- parser
- structural validator

It is intentionally designed so later modules can adopt the same pattern:

- executor
- result validator
- renderers
- PDF stage
- CLI reporting

No stage should construct untyped ad hoc exceptions once this framework is available.

## Conventions for New Stages

When adding new compiler stages:

1. Raise a typed `MdccError` subclass, not a raw `RuntimeError`.
2. Prefer `from_exception(...)` when wrapping another exception.
3. Provide `ErrorContext` whenever block/file/location context is known.
4. Populate `stdout`, `stderr`, `duration_ms`, `expected_output_type`, and `actual_output_type` when relevant.
5. Keep `message` short and human-readable.
6. Put detailed or aggregated details into `exception_message`.

## What This Document Does Not Cover

This document does not define the final CLI presentation format.

Human-readable rendering of diagnostics belongs mostly to the CLI/reporting layer and is part of later work. The current diagnostics system is the structured substrate that those reporting utilities should consume.
