from __future__ import annotations

from pathlib import Path

import pytest

from mdcc.errors import ValidationError
from mdcc.models import (
    BlockType,
    DocumentModel,
    ExecutableBlockNode,
    Frontmatter,
    MarkdownNode,
    SourceLocation,
    SourcePosition,
    SourceSpan,
    ValidationSeverity,
)
from mdcc.validator import (
    assert_valid_document_structure,
    validate_document_structure,
)


def test_validate_document_structure_accepts_valid_document() -> None:
    document = DocumentModel(
        source_path=Path("report.md"),
        frontmatter=Frontmatter(title="Memo"),
        nodes=[
            MarkdownNode(
                node_id="node-0001",
                text="# Intro\n",
                location=_location("report.md", 1, 1),
            ),
            ExecutableBlockNode(
                node_id="block-0001",
                block_type=BlockType.CHART,
                code="chart_code()\n",
                block_index=0,
                location=_location("report.md", 3, 5),
            ),
        ],
    )

    result = validate_document_structure(document)

    assert result.ok is True
    assert result.value == document
    assert result.issues == []


def test_validate_document_structure_keeps_warning_for_preserved_frontmatter_extra() -> (
    None
):
    document = DocumentModel(
        source_path=Path("report.md"),
        frontmatter=Frontmatter.model_validate({"title": "Memo", "team": "finance"}),
        nodes=[
            MarkdownNode(
                node_id="node-0001",
                text="# Intro\n",
                location=_location("report.md", 1, 1),
            )
        ],
    )

    result = validate_document_structure(document)

    assert result.ok is True
    assert len(result.issues) == 1
    assert result.issues[0].severity is ValidationSeverity.WARNING
    assert result.issues[0].code == "frontmatter-extra-preserved"


def test_validate_document_structure_rejects_duplicate_node_ids() -> None:
    location = _location("report.md", 1, 1)
    document = DocumentModel(
        source_path=Path("report.md"),
        nodes=[
            MarkdownNode(node_id="node-0001", text="A\n", location=location),
            MarkdownNode(node_id="node-0001", text="B\n", location=location),
        ],
    )

    result = validate_document_structure(document)

    assert result.ok is False
    assert any(issue.code == "node-id-duplicate" for issue in result.issues)


def test_validate_document_structure_rejects_missing_locations() -> None:
    document = DocumentModel(
        source_path=Path("report.md"),
        nodes=[MarkdownNode(node_id="node-0001", text="A\n")],
    )

    result = validate_document_structure(document)

    assert result.ok is False
    assert any(issue.code == "node-location-missing" for issue in result.issues)


def test_validate_document_structure_rejects_non_contiguous_block_indices() -> None:
    document = DocumentModel(
        source_path=Path("report.md"),
        nodes=[
            ExecutableBlockNode(
                node_id="block-0001",
                block_type=BlockType.CHART,
                code="chart_code()\n",
                block_index=1,
                location=_location("report.md", 1, 3),
            )
        ],
    )

    result = validate_document_structure(document)

    assert result.ok is False
    assert any(issue.code == "block-index-sequence-invalid" for issue in result.issues)


def test_assert_valid_document_structure_raises_structured_error() -> None:
    document = DocumentModel(
        source_path=Path("report.md"),
        nodes=[MarkdownNode(node_id="node-0001", text="")],
    )

    with pytest.raises(ValidationError) as exc_info:
        assert_valid_document_structure(document)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.message == "node node-0001 is missing source location metadata"
    assert diagnostic.exception_message is not None
    assert "node-location-missing" in diagnostic.exception_message


def _location(source_path: str, start_line: int, end_line: int) -> SourceLocation:
    return SourceLocation(
        source_path=Path(source_path),
        span=SourceSpan(
            start=SourcePosition(line=start_line, column=1),
            end=SourcePosition(line=end_line, column=1),
        ),
    )
