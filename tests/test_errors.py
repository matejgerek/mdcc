from __future__ import annotations

from pathlib import Path

import pytest

from mdcc.errors import DiagnosticCollector, ErrorContext, ParseError, ValidationError
from mdcc.models import (
    BlockType,
    Diagnostic,
    DiagnosticCategory,
    DiagnosticStage,
    SourceLocation,
    SourcePosition,
    SourceSpan,
)


def test_error_context_serializes_non_none_fields() -> None:
    context = ErrorContext(
        source_path=Path("report.md"),
        block_id="block-0001",
        block_type=BlockType.CHART,
        block_index=0,
    )

    assert context.to_fields() == {
        "source_path": Path("report.md"),
        "block_id": "block-0001",
        "block_type": BlockType.CHART,
        "block_index": 0,
    }


def test_stage_specific_error_factory_sets_defaults() -> None:
    error = ParseError.from_message(
        "unsupported block",
        context=ErrorContext(source_path=Path("report.md")),
        source_snippet="```mdcc_image",
    )

    assert error.diagnostic.stage is DiagnosticStage.PARSE
    assert error.diagnostic.category is DiagnosticCategory.PARSE_ERROR
    assert error.diagnostic.source_path == Path("report.md")
    assert error.diagnostic.source_snippet == "```mdcc_image"


def test_error_factory_captures_exception_metadata() -> None:
    cause = ValueError("boom")
    error = ValidationError.from_exception(
        "validation failed",
        cause,
        context=ErrorContext(source_path=Path("report.md")),
    )

    assert error.diagnostic.stage is DiagnosticStage.VALIDATION
    assert error.diagnostic.exception_type == "ValueError"
    assert error.diagnostic.exception_message == "boom"


def test_diagnostic_collector_raises_aggregated_error() -> None:
    collector = DiagnosticCollector()
    location = SourceLocation(
        source_path=Path("report.md"),
        span=SourceSpan(
            start=SourcePosition(line=3, column=1),
            end=SourcePosition(line=3, column=8),
        ),
    )
    collector.add(
        Diagnostic(
            stage=DiagnosticStage.VALIDATION,
            category=DiagnosticCategory.VALIDATION_ERROR,
            message="first issue",
            source_path=Path("report.md"),
            location=location,
        )
    )
    collector.add(
        Diagnostic(
            stage=DiagnosticStage.VALIDATION,
            category=DiagnosticCategory.VALIDATION_ERROR,
            message="second issue",
            source_path=Path("report.md"),
        )
    )

    with pytest.raises(ValidationError) as exc_info:
        collector.raise_if_any(ValidationError, message="document invalid")

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.message == "document invalid"
    assert diagnostic.stage is DiagnosticStage.VALIDATION
    assert diagnostic.location == location
    assert diagnostic.exception_message == "first issue; second issue"
