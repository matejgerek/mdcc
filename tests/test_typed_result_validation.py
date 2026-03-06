from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import pytest

from mdcc.errors import ValidationError
from mdcc.models import (
    BlockExecutionResult,
    BlockType,
    ChartResult,
    ExecutableBlockNode,
    ExecutionStatus,
    ExecutionStreams,
    ExecutionTiming,
    SourceLocation,
    SourcePosition,
    SourceSpan,
    TableResult,
)
from mdcc.validator import (
    assert_valid_typed_result,
    validate_typed_result,
)


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
    block_type: BlockType = BlockType.CHART,
    raw_value=None,
    raw_type_name: str | None = None,
    stdout: str = "",
    stderr: str = "",
    duration_ms: float | None = None,
) -> BlockExecutionResult:
    return BlockExecutionResult(
        block=_block(block_type),
        status=ExecutionStatus.SUCCESS,
        streams=ExecutionStreams(stdout=stdout, stderr=stderr),
        timing=ExecutionTiming(duration_ms=duration_ms, timeout_seconds=30.0),
        raw_value=raw_value,
        raw_type_name=raw_type_name,
    )


# --- Chart Tests ---


def test_validate_typed_result_accepts_valid_chart_result() -> None:
    chart = (
        alt.Chart(pd.DataFrame({"x": [1, 2], "y": [3, 4]}))
        .mark_line()
        .encode(x="x", y="y")
    )
    result = _execution_result(
        block_type=BlockType.CHART, raw_value=chart, raw_type_name="altair.Chart"
    )

    validation = validate_typed_result(result)

    assert validation.ok is True
    assert isinstance(validation.value, ChartResult)
    assert validation.value.spec["mark"]["type"] == "line"


def test_validate_typed_result_accepts_layered_chart() -> None:
    chart1 = alt.Chart(pd.DataFrame({"x": [1]})).mark_line()
    chart2 = alt.Chart(pd.DataFrame({"x": [1]})).mark_point()
    layer = alt.layer(chart1, chart2)

    result = _execution_result(
        block_type=BlockType.CHART, raw_value=layer, raw_type_name="altair.LayerChart"
    )

    validation = validate_typed_result(result)

    assert validation.ok is True
    assert isinstance(validation.value, ChartResult)


def test_validate_typed_result_accepts_concat_charts() -> None:
    chart1 = alt.Chart(pd.DataFrame({"x": [1]})).mark_line()
    chart2 = alt.Chart(pd.DataFrame({"x": [1]})).mark_point()

    for concat in (
        alt.hconcat(chart1, chart2),
        alt.vconcat(chart1, chart2),
        alt.concat(chart1, chart2),
    ):
        result = _execution_result(
            block_type=BlockType.CHART,
            raw_value=concat,
            raw_type_name=type(concat).__name__,
        )
        validation = validate_typed_result(result)
        assert validation.ok is True
        assert isinstance(validation.value, ChartResult)


def test_validate_typed_result_rejects_wrong_chart_type() -> None:
    result = _execution_result(
        block_type=BlockType.CHART,
        raw_value=pd.DataFrame({"x": [1]}),
        raw_type_name="pandas.core.frame.DataFrame",
    )

    validation = validate_typed_result(result)

    assert validation.ok is False
    assert validation.value is None
    assert validation.issues[0].code == "chart-output-invalid-type"


def test_validate_typed_result_rejects_missing_chart_expression() -> None:
    result = _execution_result(
        block_type=BlockType.CHART,
        raw_value=None,
        raw_type_name=None,
    )

    validation = validate_typed_result(result)

    assert validation.ok is False
    assert validation.issues[0].code == "chart-output-missing"
    assert (
        validation.issues[0].message == "chart block must return an Altair chart object"
    )


# --- Table Tests ---


def test_validate_typed_result_accepts_valid_table_result() -> None:
    frame = pd.DataFrame({"region": ["na", "eu"], "revenue": [10, 20]})
    result = _execution_result(
        block_type=BlockType.TABLE,
        raw_value=frame,
        raw_type_name="pandas.core.frame.DataFrame",
    )

    validation = validate_typed_result(result)

    assert validation.ok is True
    assert isinstance(validation.value, TableResult)
    assert validation.value.rows == 2
    assert validation.value.columns == ["region", "revenue"]


def test_validate_typed_result_rejects_wrong_table_type() -> None:
    result = _execution_result(
        block_type=BlockType.TABLE,
        raw_value={"region": "na"},
        raw_type_name="builtins.dict",
    )

    validation = validate_typed_result(result)

    assert validation.ok is False
    assert validation.value is None
    assert validation.issues[0].code == "table-output-invalid-type"


def test_validate_typed_result_rejects_missing_table_expression() -> None:
    result = _execution_result(
        block_type=BlockType.TABLE,
        raw_value=None,
        raw_type_name=None,
    )

    validation = validate_typed_result(result)

    assert validation.ok is False
    assert validation.issues[0].code == "table-output-missing"
    assert validation.issues[0].message == "table block must return a pandas DataFrame"


# --- Assertion and Assertion Diagnostics Tests ---


def test_assert_valid_typed_result_raises_structured_error_for_invalid_output() -> None:
    result = _execution_result(
        block_type=BlockType.TABLE,
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
    assert diagnostic.exception_message == "table-output-invalid-type"


def test_assert_valid_typed_result_uses_raw_type_name_when_value_missing() -> None:
    result = _execution_result(
        block_type=BlockType.CHART,
        raw_value=None,
        raw_type_name="builtins.generator",
    )

    with pytest.raises(ValidationError) as exc_info:
        assert_valid_typed_result(result)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.expected_output_type == "Altair chart object"
    assert diagnostic.actual_output_type == "builtins.generator"
    assert diagnostic.exception_message == "chart-output-invalid-type"


def test_coerce_typed_result_raises_type_error_on_invalid_value() -> None:
    from mdcc.validator import _coerce_typed_result

    with pytest.raises(
        TypeError, match="chart output must be validated before coercion"
    ):
        _coerce_typed_result(
            _execution_result(block_type=BlockType.CHART, raw_value="text")
        )

    with pytest.raises(
        TypeError, match="table output must be validated before coercion"
    ):
        _coerce_typed_result(
            _execution_result(block_type=BlockType.TABLE, raw_value="text")
        )
