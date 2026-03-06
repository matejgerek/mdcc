from __future__ import annotations

from pathlib import Path

from mdcc.errors import (
    ErrorContext,
    ExecutionError,
    ParseError,
    PdfGenerationError,
    ReadError,
    RenderingError,
    TimeoutError,
    ValidationError,
    format_diagnostic,
    format_unexpected_error,
)
from mdcc.models import (
    BlockType,
    DiagnosticCategory,
    DiagnosticStage,
    SourceLocation,
    SourcePosition,
    SourceSpan,
)


def test_error_classes_define_correct_stages_and_categories() -> None:
    assert ReadError.diagnostic_stage() is DiagnosticStage.READ
    assert ReadError.diagnostic_category() is DiagnosticCategory.READ_ERROR

    assert ParseError.diagnostic_stage() is DiagnosticStage.PARSE
    assert ParseError.diagnostic_category() is DiagnosticCategory.PARSE_ERROR

    assert ValidationError.diagnostic_stage() is DiagnosticStage.VALIDATION
    assert ValidationError.diagnostic_category() is DiagnosticCategory.VALIDATION_ERROR

    assert ExecutionError.diagnostic_stage() is DiagnosticStage.EXECUTION
    assert ExecutionError.diagnostic_category() is DiagnosticCategory.EXECUTION_ERROR

    assert TimeoutError.diagnostic_stage() is DiagnosticStage.TIMEOUT
    assert TimeoutError.diagnostic_category() is DiagnosticCategory.TIMEOUT_ERROR

    assert RenderingError.diagnostic_stage() is DiagnosticStage.RENDERING
    assert RenderingError.diagnostic_category() is DiagnosticCategory.RENDERING_ERROR

    assert PdfGenerationError.diagnostic_stage() is DiagnosticStage.PDF
    assert PdfGenerationError.diagnostic_category() is DiagnosticCategory.PDF_ERROR


def test_error_factory_methods_populate_diagnostic_correctly() -> None:
    context = ErrorContext(
        source_path=Path("doc.md"),
        block_id="block-001",
        block_type=BlockType.CHART,
        block_index=2,
        location=SourceLocation(
            source_path=Path("doc.md"),
            span=SourceSpan(
                start=SourcePosition(line=10, column=1),
                end=SourcePosition(line=12, column=5),
            ),
        ),
    )

    error = ParseError.from_message(
        "Invalid syntax",
        context=context,
        source_snippet="```mdcc_unknown\n",
    )

    diag = error.diagnostic
    assert diag.message == "Invalid syntax"
    assert diag.stage is DiagnosticStage.PARSE
    assert diag.category is DiagnosticCategory.PARSE_ERROR
    assert diag.source_path == Path("doc.md")
    assert diag.block_id == "block-001"
    assert diag.block_type is BlockType.CHART
    assert diag.block_index == 2
    assert diag.location == context.location
    assert diag.source_snippet == "```mdcc_unknown\n"


def test_format_diagnostic_basic_human_readable_output() -> None:
    error = ExecutionError.from_message(
        "Failed to execute",
        context=ErrorContext(source_path=Path("main.md")),
    )
    output = format_diagnostic(error.diagnostic)
    assert output == "error: Failed to execute\n  stage: execution\n  file: main.md"


def test_format_diagnostic_includes_block_reference() -> None:
    error = ValidationError.from_message(
        "Invalid block type",
        context=ErrorContext(
            block_id="block-002",
            block_type=BlockType.TABLE,
            block_index=1,
        ),
    )
    output = format_diagnostic(error.diagnostic)
    assert "error: Invalid block type" in output
    assert "  block: #1 block-002 (mdcc_table)" in output


def test_format_diagnostic_includes_location() -> None:
    error = ParseError.from_message(
        "Missing closing fence",
        context=ErrorContext(
            location=SourceLocation(
                source_path=Path("doc.md"),
                span=SourceSpan(
                    start=SourcePosition(line=5, column=1),
                    end=SourcePosition(line=5, column=10),
                ),
            )
        ),
    )
    output = format_diagnostic(error.diagnostic)
    assert "  location: line 5:1-10" in output

    error_multiline = ParseError.from_message(
        "Missing closing fence",
        context=ErrorContext(
            location=SourceLocation(
                source_path=Path("doc.md"),
                span=SourceSpan(
                    start=SourcePosition(line=5, column=1),
                    end=SourcePosition(line=10, column=3),
                ),
            )
        ),
    )
    output_multiline = format_diagnostic(error_multiline.diagnostic)
    assert "  location: lines 5:1-10:3" in output_multiline


def test_format_diagnostic_includes_multiline_snippet_and_streams() -> None:
    error = ExecutionError.from_message(
        "Execution crashed computing result",
        source_snippet="x = 1\ny = 2\n",
        stderr="Traceback:\n  File <string>\nZeroDivisionError",
        stdout="Debug output",
    )
    output = format_diagnostic(error.diagnostic, verbose=True)

    expected_snippet = "  snippet:\n    x = 1\n    y = 2"
    assert expected_snippet in output

    expected_stderr = (
        "  stderr:\n    Traceback:\n      File <string>\n    ZeroDivisionError"
    )
    assert expected_stderr in output

    assert "  stdout: Debug output" in output


def test_format_diagnostic_verbose_includes_exception_details() -> None:
    cause = ValueError("Incorrect value provided")
    error = RenderingError.from_exception(
        "Rendering failed",
        cause,
        duration_ms=45.67,
    )
    output = format_diagnostic(error.diagnostic, verbose=True)

    assert "  category: rendering_error" in output
    assert "  caused by: ValueError: Incorrect value provided" in output
    assert "  duration_ms: 45.67" in output


def test_format_diagnostic_includes_expected_actual_types() -> None:
    error = ValidationError.from_message(
        "Output type mismatch",
        expected_output_type="pandas.DataFrame",
        actual_output_type="builtins.dict",
    )
    output = format_diagnostic(error.diagnostic)
    assert "  expected: pandas.DataFrame" in output
    assert "  actual: builtins.dict" in output


def test_format_unexpected_error() -> None:
    exc = RuntimeError("System out of memory")
    basic = format_unexpected_error(exc)
    assert basic == "error: unexpected failure — RuntimeError: System out of memory"

    verbose = format_unexpected_error(exc, verbose=True)
    assert "  stage: internal" in verbose
