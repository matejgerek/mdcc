from __future__ import annotations

from pathlib import Path

import pytest

from mdcc.errors import ParseError, ReadError, ValidationError
from mdcc.models import DiagnosticCategory, DiagnosticStage
from mdcc.reader import extract_frontmatter, parse_frontmatter, read_source_document


def test_read_source_document_without_frontmatter(tmp_path: Path) -> None:
    source = tmp_path / "report.md"
    source.write_text("# Heading\n\nBody.\n", encoding="utf-8")

    result = read_source_document(source)

    assert result.source_path == source
    assert result.frontmatter is None
    assert result.frontmatter_text is None
    assert result.body_text == "# Heading\n\nBody.\n"


def test_read_source_document_with_frontmatter(tmp_path: Path) -> None:
    source = tmp_path / "report.md"
    source.write_text(
        "---\n"
        "title: Quarterly memo\n"
        "author: Finance\n"
        "date: 2026-03-06\n"
        "team: revenue\n"
        "---\n"
        "# Heading\n",
        encoding="utf-8",
    )

    result = read_source_document(source)

    assert result.frontmatter is not None
    assert result.frontmatter.title == "Quarterly memo"
    assert result.frontmatter.author == "Finance"
    assert result.frontmatter.extra == {"team": "revenue"}
    assert result.body_text == "# Heading\n"


def test_extract_frontmatter_returns_body_when_not_present() -> None:
    body = "# Heading\n---\nNot frontmatter.\n"

    frontmatter_text, body_text = extract_frontmatter(body, "report.md")

    assert frontmatter_text is None
    assert body_text == body


def test_extract_frontmatter_raises_for_unclosed_block() -> None:
    with pytest.raises(ParseError) as exc_info:
        extract_frontmatter("---\ntitle: Example\n", "report.md")

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.stage is DiagnosticStage.PARSE
    assert diagnostic.category is DiagnosticCategory.PARSE_ERROR


def test_parse_frontmatter_rejects_invalid_yaml() -> None:
    with pytest.raises(ParseError) as exc_info:
        parse_frontmatter("title: [broken\n", "report.md")

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.stage is DiagnosticStage.PARSE
    assert diagnostic.location is not None
    assert diagnostic.location.span is not None
    assert diagnostic.location.span.start.line == 3


def test_parse_frontmatter_requires_mapping_root() -> None:
    with pytest.raises(ValidationError) as exc_info:
        parse_frontmatter("- one\n- two\n", "report.md")

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.stage is DiagnosticStage.VALIDATION
    assert diagnostic.category is DiagnosticCategory.VALIDATION_ERROR
    assert diagnostic.actual_output_type == "list"


def test_read_source_document_raises_read_error_for_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.md"

    with pytest.raises(ReadError) as exc_info:
        read_source_document(missing)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.stage is DiagnosticStage.READ
    assert diagnostic.category is DiagnosticCategory.READ_ERROR
