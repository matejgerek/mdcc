from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError as PydanticValidationError

from mdcc.errors import ParseError, ReadError, ValidationError
from mdcc.models import (
    Diagnostic,
    DiagnosticCategory,
    DiagnosticStage,
    Frontmatter,
    SourceDocumentInput,
    SourceLocation,
    SourcePosition,
    SourceSpan,
)

FRONTMATTER_DELIMITER = "---"


def read_source_document(source_path: str | Path) -> SourceDocumentInput:
    path = Path(source_path)

    try:
        raw_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReadError(
            Diagnostic(
                stage=DiagnosticStage.READ,
                category=DiagnosticCategory.READ_ERROR,
                message=f"failed to read source file: {path}",
                source_path=path,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
        ) from exc

    frontmatter_text, body_text = extract_frontmatter(raw_text, path)
    frontmatter = parse_frontmatter(frontmatter_text, path)

    return SourceDocumentInput(
        source_path=path,
        raw_text=raw_text,
        body_text=body_text,
        frontmatter_text=frontmatter_text,
        frontmatter=frontmatter,
    )


def extract_frontmatter(raw_text: str, source_path: str | Path) -> tuple[str | None, str]:
    path = Path(source_path)
    lines = raw_text.splitlines(keepends=True)

    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return None, raw_text

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_DELIMITER:
            frontmatter_text = "".join(lines[1:index])
            body_text = "".join(lines[index + 1 :])
            return frontmatter_text, body_text

    raise ParseError(
        Diagnostic(
            stage=DiagnosticStage.PARSE,
            category=DiagnosticCategory.PARSE_ERROR,
            message="frontmatter opening delimiter is not closed",
            source_path=path,
            location=SourceLocation(
                source_path=path,
                span=SourceSpan(
                    start=SourcePosition(line=1, column=1),
                    end=SourcePosition(line=1, column=len(FRONTMATTER_DELIMITER)),
                ),
                snippet=FRONTMATTER_DELIMITER,
            ),
        )
    )


def parse_frontmatter(
    frontmatter_text: str | None, source_path: str | Path
) -> Frontmatter | None:
    if frontmatter_text is None:
        return None

    path = Path(source_path)
    payload = _load_frontmatter_payload(frontmatter_text, path)

    if payload is None:
        payload = {}

    if not isinstance(payload, dict):
        raise ValidationError(
            Diagnostic(
                stage=DiagnosticStage.VALIDATION,
                category=DiagnosticCategory.VALIDATION_ERROR,
                message="frontmatter must be a YAML mapping",
                source_path=path,
                source_snippet=frontmatter_text.strip() or None,
                actual_output_type=type(payload).__name__,
                expected_output_type="dict",
            )
        )

    try:
        return Frontmatter.model_validate(payload)
    except PydanticValidationError as exc:
        raise ValidationError(
            Diagnostic(
                stage=DiagnosticStage.VALIDATION,
                category=DiagnosticCategory.VALIDATION_ERROR,
                message="frontmatter failed validation",
                source_path=path,
                source_snippet=frontmatter_text.strip() or None,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
        ) from exc


def _load_frontmatter_payload(frontmatter_text: str, source_path: Path) -> object:
    try:
        return yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = None
        if mark is not None:
            line = mark.line + 2
            column = mark.column + 1
            location = SourceLocation(
                source_path=source_path,
                span=SourceSpan(
                    start=SourcePosition(line=line, column=column),
                    end=SourcePosition(line=line, column=column),
                ),
            )

        raise ParseError(
            Diagnostic(
                stage=DiagnosticStage.PARSE,
                category=DiagnosticCategory.PARSE_ERROR,
                message="frontmatter contains invalid YAML",
                source_path=source_path,
                location=location,
                source_snippet=frontmatter_text.strip() or None,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
        ) from exc


__all__ = ["extract_frontmatter", "parse_frontmatter", "read_source_document"]
