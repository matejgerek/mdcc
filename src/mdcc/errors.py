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


__all__ = [
    "DiagnosticCollector",
    "ErrorContext",
    "ExecutionError",
    "MdccError",
    "ParseError",
    "PdfGenerationError",
    "ReadError",
    "RenderingError",
    "TimeoutError",
    "ValidationError",
]
