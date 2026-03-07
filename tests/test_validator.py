from __future__ import annotations

from pathlib import Path

import pytest

from mdcc.errors import ValidationError
from mdcc.models import (
    BlockType,
    BlockMetadata,
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
                metadata=BlockMetadata(),
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
                metadata=BlockMetadata(),
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


def test_validate_document_structure_normalizes_valid_block_metadata() -> None:
    block = ExecutableBlockNode(
        node_id="block-0001",
        block_type=BlockType.TABLE,
        code="frame\n",
        block_index=0,
        raw_metadata=(
            ("caption", "  Regional summary  "),
            ("label", "tbl:summary"),
        ),
        location=_location("report.md", 3, 5),
    )
    document = DocumentModel(source_path=Path("report.md"), nodes=[block])

    result = validate_document_structure(document)

    assert result.ok is True
    assert block.metadata == BlockMetadata(
        caption="Regional summary",
        label="tbl:summary",
    )


def test_validate_document_structure_rejects_duplicate_block_metadata_keys() -> None:
    document = DocumentModel(
        source_path=Path("report.md"),
        nodes=[
            ExecutableBlockNode(
                node_id="block-0001",
                block_type=BlockType.CHART,
                code="chart\n",
                block_index=0,
                raw_metadata=(("caption", "A"), ("caption", "B")),
                location=_location("report.md", 3, 5),
            )
        ],
    )

    result = validate_document_structure(document)

    assert result.ok is False
    assert any(issue.code == "block-metadata-key-duplicate" for issue in result.issues)
    assert any(
        issue.message == "duplicate metadata key 'caption'" for issue in result.issues
    )
    assert all(issue.location == document.nodes[0].location for issue in result.issues)


def test_validate_document_structure_rejects_unknown_block_metadata_keys() -> None:
    document = DocumentModel(
        source_path=Path("report.md"),
        nodes=[
            ExecutableBlockNode(
                node_id="block-0001",
                block_type=BlockType.CHART,
                code="chart\n",
                block_index=0,
                raw_metadata=(("width", "wide"),),
                location=_location("report.md", 3, 5),
            )
        ],
    )

    result = validate_document_structure(document)

    assert result.ok is False
    assert any(issue.code == "block-metadata-key-unknown" for issue in result.issues)
    assert any(
        issue.message
        == "unsupported metadata key 'width' for mdcc_chart in this compiler version"
        for issue in result.issues
    )


def test_validate_document_structure_rejects_empty_caption() -> None:
    document = DocumentModel(
        source_path=Path("report.md"),
        nodes=[
            ExecutableBlockNode(
                node_id="block-0001",
                block_type=BlockType.TABLE,
                code="frame\n",
                block_index=0,
                raw_metadata=(("caption", "   "),),
                location=_location("report.md", 3, 5),
            )
        ],
    )

    result = validate_document_structure(document)

    assert result.ok is False
    assert any(issue.code == "block-metadata-caption-empty" for issue in result.issues)
    assert any(issue.message == "caption must not be empty" for issue in result.issues)


def test_validate_document_structure_rejects_invalid_label() -> None:
    document = DocumentModel(
        source_path=Path("report.md"),
        nodes=[
            ExecutableBlockNode(
                node_id="block-0001",
                block_type=BlockType.TABLE,
                code="frame\n",
                block_index=0,
                raw_metadata=(("label", "regional summary"),),
                location=_location("report.md", 3, 5),
            )
        ],
    )

    result = validate_document_structure(document)

    assert result.ok is False
    assert any(issue.code == "block-metadata-label-invalid" for issue in result.issues)
    assert any(
        issue.message
        == "invalid label 'regional summary'; expected pattern ^[A-Za-z][A-Za-z0-9:_-]*$"
        for issue in result.issues
    )


def _location(source_path: str, start_line: int, end_line: int) -> SourceLocation:
    return SourceLocation(
        source_path=Path(source_path),
        span=SourceSpan(
            start=SourcePosition(line=start_line, column=1),
            end=SourcePosition(line=end_line, column=1),
        ),
    )
