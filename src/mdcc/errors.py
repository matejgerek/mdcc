from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from mdcc.models import (
    BlockType,
    Diagnostic,
    DiagnosticCategory,
    DiagnosticStage,
    SourceLocation,
)

MdccErrorT = TypeVar("MdccErrorT", bound="MdccError")


@dataclass(frozen=True, slots=True)
class ErrorContext:
    source_path: Path | None = None
    block_id: str | None = None
    block_type: BlockType | None = None
    block_index: int | None = None
    location: SourceLocation | None = None

    def to_fields(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "source_path": self.source_path,
                "block_id": self.block_id,
                "block_type": self.block_type,
                "block_index": self.block_index,
                "location": self.location,
            }.items()
            if value is not None
        }


class MdccError(Exception):
    def __init__(self, diagnostic: Diagnostic):
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic

    @classmethod
    def diagnostic_stage(cls) -> DiagnosticStage | None:
        return None

    @classmethod
    def diagnostic_category(cls) -> DiagnosticCategory | None:
        return None

    @classmethod
    def from_message(
        cls: type[MdccErrorT],
        message: str,
        *,
        context: ErrorContext | None = None,
        stage: DiagnosticStage | None = None,
        category: DiagnosticCategory | None = None,
        **extra: Any,
    ) -> MdccErrorT:
        resolved_stage = stage or cls.diagnostic_stage()
        resolved_category = category or cls.diagnostic_category()
        if resolved_stage is None or resolved_category is None:
            msg = "diagnostic stage and category must be provided"
            raise ValueError(msg)

        fields = context.to_fields() if context is not None else {}
        fields.update(extra)

        return cls(
            Diagnostic(
                stage=resolved_stage,
                category=resolved_category,
                message=message,
                **fields,
            )
        )

    @classmethod
    def from_exception(
        cls: type[MdccErrorT],
        message: str,
        cause: BaseException,
        *,
        context: ErrorContext | None = None,
        stage: DiagnosticStage | None = None,
        category: DiagnosticCategory | None = None,
        **extra: Any,
    ) -> MdccErrorT:
        return cls.from_message(
            message,
            context=context,
            stage=stage,
            category=category,
            exception_type=type(cause).__name__,
            exception_message=str(cause),
            **extra,
        )


class ReadError(MdccError):
    @classmethod
    def diagnostic_stage(cls) -> DiagnosticStage:
        return DiagnosticStage.READ

    @classmethod
    def diagnostic_category(cls) -> DiagnosticCategory:
        return DiagnosticCategory.READ_ERROR


class ParseError(MdccError):
    @classmethod
    def diagnostic_stage(cls) -> DiagnosticStage:
        return DiagnosticStage.PARSE

    @classmethod
    def diagnostic_category(cls) -> DiagnosticCategory:
        return DiagnosticCategory.PARSE_ERROR


class ValidationError(MdccError):
    @classmethod
    def diagnostic_stage(cls) -> DiagnosticStage:
        return DiagnosticStage.VALIDATION

    @classmethod
    def diagnostic_category(cls) -> DiagnosticCategory:
        return DiagnosticCategory.VALIDATION_ERROR


class ExecutionError(MdccError):
    @classmethod
    def diagnostic_stage(cls) -> DiagnosticStage:
        return DiagnosticStage.EXECUTION

    @classmethod
    def diagnostic_category(cls) -> DiagnosticCategory:
        return DiagnosticCategory.EXECUTION_ERROR


class TimeoutError(MdccError):
    @classmethod
    def diagnostic_stage(cls) -> DiagnosticStage:
        return DiagnosticStage.TIMEOUT

    @classmethod
    def diagnostic_category(cls) -> DiagnosticCategory:
        return DiagnosticCategory.TIMEOUT_ERROR


class RenderingError(MdccError):
    @classmethod
    def diagnostic_stage(cls) -> DiagnosticStage:
        return DiagnosticStage.RENDERING

    @classmethod
    def diagnostic_category(cls) -> DiagnosticCategory:
        return DiagnosticCategory.RENDERING_ERROR


class PdfGenerationError(MdccError):
    @classmethod
    def diagnostic_stage(cls) -> DiagnosticStage:
        return DiagnosticStage.PDF

    @classmethod
    def diagnostic_category(cls) -> DiagnosticCategory:
        return DiagnosticCategory.PDF_ERROR


class BundleError(MdccError):
    @classmethod
    def diagnostic_stage(cls) -> DiagnosticStage:
        return DiagnosticStage.BUNDLE

    @classmethod
    def diagnostic_category(cls) -> DiagnosticCategory:
        return DiagnosticCategory.BUNDLE_ERROR


class BundleValidationError(MdccError):
    @classmethod
    def diagnostic_stage(cls) -> DiagnosticStage:
        return DiagnosticStage.BUNDLE

    @classmethod
    def diagnostic_category(cls) -> DiagnosticCategory:
        return DiagnosticCategory.BUNDLE_VALIDATION_ERROR


class InspectionError(MdccError):
    @classmethod
    def diagnostic_stage(cls) -> DiagnosticStage:
        return DiagnosticStage.INSPECTION

    @classmethod
    def diagnostic_category(cls) -> DiagnosticCategory:
        return DiagnosticCategory.INSPECTION_ERROR


class SqlExecutionError(MdccError):
    @classmethod
    def diagnostic_stage(cls) -> DiagnosticStage:
        return DiagnosticStage.SQL

    @classmethod
    def diagnostic_category(cls) -> DiagnosticCategory:
        return DiagnosticCategory.SQL_ERROR


class DiagnosticCollector:
    def __init__(self) -> None:
        self._diagnostics: list[Diagnostic] = []

    def add(self, diagnostic: Diagnostic) -> None:
        self._diagnostics.append(diagnostic)

    def extend(self, diagnostics: list[Diagnostic]) -> None:
        self._diagnostics.extend(diagnostics)

    @property
    def diagnostics(self) -> list[Diagnostic]:
        return list(self._diagnostics)

    def has_errors(self) -> bool:
        return bool(self._diagnostics)

    def raise_if_any(
        self,
        error_cls: type[MdccError],
        *,
        message: str | None = None,
    ) -> None:
        if not self._diagnostics:
            return

        primary = self._diagnostics[0]
        raise error_cls.from_message(
            message or primary.message,
            context=ErrorContext(
                source_path=primary.source_path,
                block_id=primary.block_id,
                block_type=primary.block_type,
                block_index=primary.block_index,
                location=primary.location,
            ),
            source_snippet=primary.source_snippet,
            stdout=primary.stdout,
            stderr=primary.stderr,
            exception_type=primary.exception_type,
            exception_message="; ".join(
                diagnostic.message for diagnostic in self._diagnostics
            ),
        )


def format_diagnostic(diagnostic: Diagnostic, *, verbose: bool = False) -> str:
    lines = [f"error: {diagnostic.message}", f"  stage: {diagnostic.stage.value}"]

    if verbose:
        lines.append(f"  category: {diagnostic.category.value}")

    if diagnostic.source_path is not None:
        lines.append(f"  file: {diagnostic.source_path}")

    block_reference = _format_block_reference(diagnostic)
    if block_reference is not None:
        lines.append(f"  block: {block_reference}")

    location = _format_location(diagnostic.location)
    if location is not None:
        lines.append(f"  location: {location}")

    snippet = diagnostic.source_snippet or (
        diagnostic.location.snippet if diagnostic.location is not None else None
    )
    if snippet:
        lines.extend(_format_multiline_field("snippet", snippet))

    if diagnostic.expected_output_type is not None:
        lines.append(f"  expected: {diagnostic.expected_output_type}")

    if diagnostic.actual_output_type is not None:
        lines.append(f"  actual: {diagnostic.actual_output_type}")

    if diagnostic.stderr:
        lines.extend(_format_multiline_field("stderr", diagnostic.stderr))

    if verbose and diagnostic.stdout:
        lines.extend(_format_multiline_field("stdout", diagnostic.stdout))

    if verbose and diagnostic.exception_type is not None:
        if diagnostic.exception_message:
            lines.append(
                f"  caused by: {diagnostic.exception_type}: {diagnostic.exception_message}"
            )
        else:
            lines.append(f"  caused by: {diagnostic.exception_type}")

    if verbose and diagnostic.duration_ms is not None:
        lines.append(f"  duration_ms: {diagnostic.duration_ms:.2f}")

    return "\n".join(lines)


def format_unexpected_error(exc: Exception, *, verbose: bool = False) -> str:
    lines = [f"error: unexpected failure — {type(exc).__name__}: {exc}"]
    if verbose:
        lines.append("  stage: internal")
    return "\n".join(lines)


def _format_block_reference(diagnostic: Diagnostic) -> str | None:
    parts: list[str] = []
    if diagnostic.block_index is not None:
        parts.append(f"#{diagnostic.block_index}")
    if diagnostic.block_id is not None:
        parts.append(diagnostic.block_id)
    if diagnostic.block_type is not None:
        parts.append(f"({diagnostic.block_type.value})")
    return " ".join(parts) if parts else None


def _format_location(location: SourceLocation | None) -> str | None:
    if location is None or location.span is None:
        return None

    start = location.span.start
    end = location.span.end
    if (start.line, start.column) == (end.line, end.column):
        return f"line {start.line}:{start.column}"
    if start.line == end.line:
        return f"line {start.line}:{start.column}-{end.column}"
    return f"lines {start.line}:{start.column}-{end.line}:{end.column}"


def _format_multiline_field(label: str, value: str) -> list[str]:
    stripped = value.rstrip()
    if "\n" not in stripped:
        return [f"  {label}: {stripped}"]

    lines = [f"  {label}:"]
    lines.extend(f"    {line}" for line in stripped.splitlines())
    return lines


__all__ = [
    "DiagnosticCollector",
    "ErrorContext",
    "ExecutionError",
    "format_diagnostic",
    "format_unexpected_error",
    "MdccError",
    "ParseError",
    "PdfGenerationError",
    "ReadError",
    "RenderingError",
    "TimeoutError",
    "ValidationError",
]
