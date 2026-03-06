from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import pytest

from mdcc.errors import ValidationError
from mdcc.models import (
    BlockType,
    BlockExecutionResult,
    ChartResult,
    DocumentModel,
    ExecutableBlockNode,
    Frontmatter,
    MarkdownNode,
    TableResult,
    ExecutionStatus,
    ExecutionStreams,
    ExecutionTiming,
    SourceLocation,
    SourcePosition,
    SourceSpan,
    ValidationSeverity,
)
from mdcc.validator import (
    assert_valid_document_structure,
    assert_valid_typed_result,
    validate_document_structure,
    validate_typed_result,
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


def test_validate_typed_result_accepts_valid_chart_result() -> None:
    block = _block(block_type=BlockType.CHART)
    chart = (
        alt.Chart(pd.DataFrame({"x": [1, 2], "y": [3, 4]}))
        .mark_line()
        .encode(x="x", y="y")
    )
    result = _execution_result(
        block=block, raw_value=chart, raw_type_name="altair.Chart"
    )

    validation = validate_typed_result(result)

    assert validation.ok is True
    assert isinstance(validation.value, ChartResult)
    assert validation.value.spec["mark"]["type"] == "line"


def test_validate_typed_result_accepts_valid_table_result() -> None:
    block = _block(block_type=BlockType.TABLE)
    frame = pd.DataFrame({"region": ["na", "eu"], "revenue": [10, 20]})
    result = _execution_result(
        block=block,
        raw_value=frame,
        raw_type_name="pandas.core.frame.DataFrame",
    )

    validation = validate_typed_result(result)

    assert validation.ok is True
    assert isinstance(validation.value, TableResult)
    assert validation.value.rows == 2
    assert validation.value.columns == ["region", "revenue"]


def test_validate_typed_result_rejects_wrong_chart_type() -> None:
    result = _execution_result(
        block=_block(block_type=BlockType.CHART),
        raw_value=pd.DataFrame({"x": [1]}),
        raw_type_name="pandas.core.frame.DataFrame",
    )

    validation = validate_typed_result(result)

    assert validation.ok is False
    assert validation.value is None
    assert validation.issues[0].code == "chart-output-invalid-type"


def test_validate_typed_result_rejects_missing_table_expression() -> None:
    result = _execution_result(
        block=_block(block_type=BlockType.TABLE),
        raw_value=None,
        raw_type_name=None,
    )

    validation = validate_typed_result(result)

    assert validation.ok is False
    assert validation.issues[0].code == "table-output-missing"


def test_assert_valid_typed_result_raises_structured_error_for_invalid_output() -> None:
    result = _execution_result(
        block=_block(block_type=BlockType.TABLE),
        raw_value=42,
        raw_type_name="builtins.int",
        stdout="debug line\n",
        stderr="",
        duration_ms=12.5,
    )

    with pytest.raises(ValidationError) as exc_info:
        assert_valid_typed_result(result)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.message == "table block must return a pandas DataFrame"
    assert diagnostic.block_type is BlockType.TABLE
    assert diagnostic.expected_output_type == "pandas.DataFrame"
    assert diagnostic.actual_output_type == "builtins.int"
    assert diagnostic.stdout == "debug line\n"
    assert diagnostic.duration_ms == 12.5


def test_assert_valid_typed_result_uses_raw_type_name_when_value_missing() -> None:
    result = _execution_result(
        block=_block(block_type=BlockType.CHART),
        raw_value=None,
        raw_type_name="builtins.generator",
    )

    with pytest.raises(ValidationError) as exc_info:
        assert_valid_typed_result(result)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.expected_output_type == "Altair chart object"
    assert diagnostic.actual_output_type == "builtins.generator"


def _location(source_path: str, start_line: int, end_line: int) -> SourceLocation:
    return SourceLocation(
        source_path=Path(source_path),
        span=SourceSpan(
            start=SourcePosition(line=start_line, column=1),
            end=SourcePosition(line=end_line, column=1),
        ),
    )


def _block(block_type: BlockType) -> ExecutableBlockNode:
    return ExecutableBlockNode(
        node_id="block-0001",
        block_type=block_type,
        code="value\n",
        block_index=0,
        location=_location("report.md", 3, 5),
    )


def _execution_result(
    *,
    block: ExecutableBlockNode,
    raw_value,
    raw_type_name: str | None,
    stdout: str = "",
    stderr: str = "",
    duration_ms: float | None = None,
) -> BlockExecutionResult:
    return BlockExecutionResult(
        block=block,
        status=ExecutionStatus.SUCCESS,
        streams=ExecutionStreams(stdout=stdout, stderr=stderr),
        timing=ExecutionTiming(duration_ms=duration_ms, timeout_seconds=30.0),
        raw_value=raw_value,
        raw_type_name=raw_type_name,
    )
