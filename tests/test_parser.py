from __future__ import annotations

from pathlib import Path

import pytest

from mdcc.errors import ParseError
from mdcc.models import BlockType, ExecutableBlockNode, MarkdownNode, SourceDocumentInput
from mdcc.parser import parse_document


def test_parse_document_with_markdown_and_executable_blocks() -> None:
    source = SourceDocumentInput(
        source_path=Path("report.md"),
        raw_text="",
        body_text=(
            "# Revenue\n\n"
            "Intro paragraph.\n\n"
            "```mdcc_chart\n"
            "chart_code()\n"
            "```\n\n"
            "Between blocks.\n\n"
            "```mdcc_table\n"
            "table_code()\n"
            "```\n"
        ),
    )

    document = parse_document(source)

    assert [type(node) for node in document.nodes] == [
        MarkdownNode,
        ExecutableBlockNode,
        MarkdownNode,
        ExecutableBlockNode,
    ]
    assert document.nodes[1].block_type is BlockType.CHART
    assert document.nodes[1].block_index == 0
    assert document.nodes[1].code == "chart_code()\n"
    assert document.nodes[3].block_type is BlockType.TABLE
    assert document.nodes[3].block_index == 1


def test_parse_document_preserves_regular_markdown_fences() -> None:
    source = SourceDocumentInput(
        source_path=Path("report.md"),
        raw_text="",
        body_text=(
            "```python\n"
            "print('hello')\n"
            "```mdcc_chart\n"
            "still markdown\n"
            "```\n"
            "```\n"
        ),
    )

    document = parse_document(source)

    assert len(document.nodes) == 1
    assert isinstance(document.nodes[0], MarkdownNode)
    assert "```mdcc_chart" in document.nodes[0].text


def test_parse_document_rejects_unsupported_mdcc_block_type() -> None:
    source = SourceDocumentInput(
        source_path=Path("report.md"),
        raw_text="",
        body_text="```mdcc_image\ncontent\n```\n",
    )

    with pytest.raises(ParseError) as exc_info:
        parse_document(source)

    assert "unsupported or malformed executable block fence" in str(exc_info.value)


def test_parse_document_rejects_executable_fence_metadata() -> None:
    source = SourceDocumentInput(
        source_path=Path("report.md"),
        raw_text="",
        body_text='```mdcc_chart width="wide"\ncontent\n```\n',
    )

    with pytest.raises(ParseError) as exc_info:
        parse_document(source)

    assert "unsupported or malformed executable block fence" in str(exc_info.value)


def test_parse_document_rejects_unclosed_executable_fence() -> None:
    source = SourceDocumentInput(
        source_path=Path("report.md"),
        raw_text="",
        body_text="```mdcc_chart\nchart_code()\n",
    )

    with pytest.raises(ParseError) as exc_info:
        parse_document(source)

    assert "executable block fence is not closed" in str(exc_info.value)


def test_parse_document_preserves_node_source_locations() -> None:
    source = SourceDocumentInput(
        source_path=Path("report.md"),
        raw_text="",
        body_text="Intro\n\n```mdcc_chart\nchart_code()\n```\n",
    )

    document = parse_document(source)
    markdown_node = document.nodes[0]
    block_node = document.nodes[1]

    assert markdown_node.location is not None
    assert markdown_node.location.span is not None
    assert markdown_node.location.span.start.line == 1
    assert markdown_node.location.span.end.line == 2

    assert block_node.location is not None
    assert block_node.location.span is not None
    assert block_node.location.span.start.line == 3
    assert block_node.location.span.end.line == 5


def test_parse_document_skips_empty_markdown_between_consecutive_blocks() -> None:
    source = SourceDocumentInput(
        source_path=Path("report.md"),
        raw_text="",
        body_text=(
            "```mdcc_chart\nchart_code()\n```\n"
            "```mdcc_table\ntable_code()\n```\n"
        ),
    )

    document = parse_document(source)

    assert len(document.nodes) == 2
    assert all(isinstance(node, ExecutableBlockNode) for node in document.nodes)
