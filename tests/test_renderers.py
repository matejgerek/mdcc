from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import pytest
import vl_convert as vlc

from mdcc.errors import RenderingError
from mdcc.models import (
    ArtifactKind,
    BlockType,
    ChartResult,
    ExecutableBlockNode,
    SourceLocation,
    SourcePosition,
    SourceSpan,
    TableResult,
)
from mdcc.renderers import (
    render_chart_artifact,
    render_table_artifact,
    render_typed_result,
)
from mdcc.utils.workspace import BuildContext


def _source_file(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "report.md"
    source.write_text("# report\n", encoding="utf-8")
    return source


def _location(source_path: Path, line: int, snippet: str) -> SourceLocation:
    return SourceLocation(
        source_path=source_path,
        span=SourceSpan(
            start=SourcePosition(line=line, column=1),
            end=SourcePosition(line=line, column=12),
        ),
        snippet=snippet,
    )


def _block(
    *,
    source_path: Path,
    index: int,
    block_type: BlockType,
    code: str,
) -> ExecutableBlockNode:
    return ExecutableBlockNode(
        node_id=f"block-{index + 1:04d}",
        block_type=block_type,
        code=code,
        block_index=index,
        location=_location(source_path, index + 1, code.strip()),
    )


def _chart_result(tmp_path: Path) -> ChartResult:
    source = _source_file(tmp_path)
    block = _block(
        source_path=source,
        index=0,
        block_type=BlockType.CHART,
        code="alt.Chart(data).mark_line().encode(x='x', y='y')",
    )
    chart = (
        alt.Chart(pd.DataFrame({"x": [1, 2], "y": [3, 4]}))
        .mark_line()
        .encode(x="x", y="y")
    )
    return ChartResult(block=block, value=chart, spec=chart.to_dict())


def _table_result(tmp_path: Path) -> TableResult:
    source = _source_file(tmp_path)
    block = _block(
        source_path=source,
        index=0,
        block_type=BlockType.TABLE,
        code="frame",
    )
    frame = pd.DataFrame({"region": ["na", "eu"], "revenue": [10, 20]})
    return TableResult(block=block, value=frame)


def test_render_chart_artifact_writes_svg_and_preserves_block_metadata(
    tmp_path: Path,
) -> None:
    result = _chart_result(tmp_path)
    assert result.block.location is not None
    build_context = BuildContext.create(result.block.location.source_path, keep=True)

    artifact = render_chart_artifact(result, build_context)

    assert artifact.artifact_id == "chart-block-0001"
    assert artifact.kind is ArtifactKind.CHART
    assert artifact.block == result.block
    assert artifact.block.block_type is BlockType.CHART
    assert artifact.block.block_index == 0
    assert artifact.path == build_context.chart_path(0, ".svg")
    assert artifact.mime_type == "image/svg+xml"
    assert artifact.html is None
    assert artifact.path is not None
    assert artifact.path.exists()
    svg = artifact.path.read_text(encoding="utf-8")
    assert svg.startswith("<svg")


def test_render_table_artifact_writes_html_and_preserves_block_metadata(
    tmp_path: Path,
) -> None:
    result = _table_result(tmp_path)
    assert result.block.location is not None
    build_context = BuildContext.create(result.block.location.source_path, keep=True)

    artifact = render_table_artifact(result, build_context)

    assert artifact.artifact_id == "table-block-0001"
    assert artifact.kind is ArtifactKind.TABLE
    assert artifact.block == result.block
    assert artifact.block.block_type is BlockType.TABLE
    assert artifact.block.block_index == 0
    assert artifact.path == build_context.table_path(0, ".html")
    assert artifact.mime_type == "text/html"
    assert artifact.html is not None
    assert "<table" in artifact.html
    assert "region" in artifact.html
    assert artifact.path is not None
    assert artifact.path.read_text(encoding="utf-8") == artifact.html


def test_render_typed_result_dispatches_chart_and_table_results(
    tmp_path: Path,
) -> None:
    chart_result = _chart_result(tmp_path / "chart_case")
    assert chart_result.block.location is not None
    chart_build_context = BuildContext.create(
        chart_result.block.location.source_path,
        keep=True,
    )
    chart_artifact = render_typed_result(chart_result, chart_build_context)

    table_result = _table_result(tmp_path / "table_case")
    assert table_result.block.location is not None
    table_build_context = BuildContext.create(
        table_result.block.location.source_path,
        keep=True,
    )
    table_artifact = render_typed_result(table_result, table_build_context)

    assert chart_artifact.kind is ArtifactKind.CHART
    assert chart_artifact.mime_type == "image/svg+xml"
    assert table_artifact.kind is ArtifactKind.TABLE
    assert table_artifact.mime_type == "text/html"


def test_render_chart_artifact_raises_structured_rendering_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _chart_result(tmp_path)
    assert result.block.location is not None
    build_context = BuildContext.create(result.block.location.source_path, keep=True)

    def _boom(spec: dict[str, object]) -> str:
        raise RuntimeError("svg conversion failed")

    monkeypatch.setattr(vlc, "vegalite_to_svg", _boom)

    with pytest.raises(RenderingError) as exc_info:
        render_chart_artifact(result, build_context)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.message == "failed to render chart artifact"
    assert diagnostic.block_id == result.block.node_id
    assert diagnostic.block_type is BlockType.CHART
    assert diagnostic.block_index == result.block.block_index
    assert diagnostic.source_path == result.block.location.source_path
    assert diagnostic.location == result.block.location
    assert result.block.location.snippet is not None
    assert diagnostic.source_snippet == result.block.location.snippet
    assert diagnostic.exception_type == "RuntimeError"
    assert diagnostic.exception_message == "svg conversion failed"


def test_render_table_artifact_raises_structured_rendering_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _table_result(tmp_path)
    assert result.block.location is not None
    build_context = BuildContext.create(result.block.location.source_path, keep=True)

    def _boom(
        self: pd.DataFrame,
        buf: object | None = None,
        *,
        columns: object | None = None,
        col_space: object | None = None,
        header: bool = True,
        index: bool = True,
        na_rep: str = "NaN",
        formatters: object | None = None,
        float_format: object | None = None,
        sparsify: bool | None = None,
        index_names: bool = True,
        justify: object | None = None,
        max_rows: int | None = None,
        max_cols: int | None = None,
        show_dimensions: bool | str = False,
        decimal: str = ".",
        bold_rows: bool = True,
        classes: object | None = None,
        escape: bool = True,
        notebook: bool = False,
        border: int | bool | None = None,
        table_id: str | None = None,
        render_links: bool = False,
        encoding: str | None = None,
    ) -> str:
        raise OSError("disk full")

    monkeypatch.setattr(pd.DataFrame, "to_html", _boom)

    with pytest.raises(RenderingError) as exc_info:
        render_table_artifact(result, build_context)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.message == "failed to render table artifact"
    assert diagnostic.block_id == result.block.node_id
    assert diagnostic.block_type is BlockType.TABLE
    assert diagnostic.block_index == result.block.block_index
    assert diagnostic.source_path == result.block.location.source_path
    assert diagnostic.location == result.block.location
    assert result.block.location.snippet is not None
    assert diagnostic.source_snippet == result.block.location.snippet
    assert diagnostic.exception_type == "OSError"
    assert diagnostic.exception_message == "disk full"
