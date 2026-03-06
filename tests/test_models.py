from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import pytest

from mdcc.errors import ValidationError
from mdcc.models import (
    ArtifactKind,
    AssembledDocumentNode,
    BlockType,
    ChartResult,
    Diagnostic,
    DiagnosticCategory,
    DiagnosticStage,
    ExecutableBlockNode,
    Frontmatter,
    MarkdownNode,
    NodeKind,
    SourceLocation,
    SourcePosition,
    SourceSpan,
    TableResult,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)


def test_frontmatter_preserves_unknown_fields_in_extra() -> None:
    frontmatter = Frontmatter.model_validate(
        {
            "title": "Quarterly update",
            "author": "Analyst",
            "date": "2026-03-06",
            "team": "finance",
            "revision": 3,
        }
    )

    assert frontmatter.title == "Quarterly update"
    assert frontmatter.extra == {"team": "finance", "revision": 3}


def test_source_span_rejects_reverse_ranges() -> None:
    with pytest.raises(ValueError):
        SourceSpan(
            start=SourcePosition(line=10, column=1),
            end=SourcePosition(line=9, column=20),
        )


def test_table_result_populates_summary_fields_from_dataframe() -> None:
    block = ExecutableBlockNode(
        node_id="block-001",
        block_type=BlockType.TABLE,
        code="df",
        block_index=0,
    )
    frame = pd.DataFrame({"region": ["na", "eu"], "revenue": [10, 20]})

    result = TableResult(block=block, value=frame)

    assert result.category is ArtifactKind.TABLE
    assert result.rows == 2
    assert result.columns == ["region", "revenue"]


def test_chart_result_accepts_altair_chart_objects() -> None:
    block = ExecutableBlockNode(
        node_id="block-002",
        block_type=BlockType.CHART,
        code="chart",
        block_index=1,
    )
    chart = (
        alt.Chart(pd.DataFrame({"x": [1, 2], "y": [3, 4]}))
        .mark_line()
        .encode(
            x="x",
            y="y",
        )
    )

    result = ChartResult(block=block, value=chart, spec=chart.to_dict())

    assert result.category is ArtifactKind.CHART
    assert result.spec["mark"]["type"] == "line"


def test_assembled_document_node_requires_exactly_one_payload() -> None:
    markdown = MarkdownNode(node_id="node-001", text="Intro")

    with pytest.raises(ValueError):
        AssembledDocumentNode(kind=NodeKind.MARKDOWN)

    node = AssembledDocumentNode(kind=NodeKind.MARKDOWN, markdown=markdown)
    assert node.markdown == markdown


def test_validation_result_preserves_typed_value_and_issues() -> None:
    issue = ValidationIssue(
        severity=ValidationSeverity.WARNING,
        code="frontmatter-unknown-field",
        message="unknown field preserved in extra",
    )

    result = ValidationResult[Frontmatter](
        ok=True,
        value=Frontmatter(title="Memo"),
        issues=[issue],
    )

    assert result.ok is True
    assert result.value is not None
    assert result.value.title == "Memo"
    assert result.issues == [issue]


def test_validation_error_wraps_diagnostic() -> None:
    diagnostic = Diagnostic(
        stage=DiagnosticStage.VALIDATION,
        category=DiagnosticCategory.VALIDATION_ERROR,
        message="final expression returned None",
        source_path=Path("report.md"),
        block_id="block-003",
        block_type=BlockType.TABLE,
        location=SourceLocation(source_path=Path("report.md")),
    )

    error = ValidationError(diagnostic)

    assert str(error) == "final expression returned None"
    assert error.diagnostic == diagnostic
