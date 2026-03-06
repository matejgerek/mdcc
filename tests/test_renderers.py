from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import pytest
import vl_convert as vlc

from mdcc.errors import RenderingError
from mdcc.models import (
    AssembledDocumentNode,
    ArtifactKind,
    BlockType,
    ChartResult,
    DocumentModel,
    ExecutableBlockNode,
    Frontmatter,
    IntermediateDocument,
    MarkdownNode,
    NodeKind,
    RenderedArtifact,
    SourceLocation,
    SourcePosition,
    SourceSpan,
    TableResult,
)
from mdcc.renderers import (
    assemble_document,
    render_chart_artifact,
    render_intermediate_document,
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


def _markdown_node(
    *,
    source_path: Path,
    node_id: str,
    line: int,
    text: str,
) -> MarkdownNode:
    return MarkdownNode(
        node_id=node_id,
        text=text,
        location=_location(source_path, line, text.strip()),
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


def _chart_and_table_document(
    tmp_path: Path,
) -> tuple[DocumentModel, ChartResult, TableResult, BuildContext]:
    source = _source_file(tmp_path)
    intro = _markdown_node(
        source_path=source,
        node_id="node-0001",
        line=1,
        text="# Intro\n",
    )
    chart_block = _block(
        source_path=source,
        index=0,
        block_type=BlockType.CHART,
        code="chart",
    )
    bridge = _markdown_node(
        source_path=source,
        node_id="node-0002",
        line=3,
        text="Bridge paragraph\n",
    )
    table_block = _block(
        source_path=source,
        index=1,
        block_type=BlockType.TABLE,
        code="frame",
    )
    document = DocumentModel(
        source_path=source,
        frontmatter=Frontmatter(title="Report"),
        nodes=[intro, chart_block, bridge, table_block],
    )
    chart = (
        alt.Chart(pd.DataFrame({"x": [1, 2], "y": [3, 4]}))
        .mark_line()
        .encode(x="x", y="y")
    )
    chart_result = ChartResult(block=chart_block, value=chart, spec=chart.to_dict())
    table_result = TableResult(
        block=table_block,
        value=pd.DataFrame({"region": ["na", "eu"], "revenue": [10, 20]}),
    )
    build_context = BuildContext.create(source, keep=True)
    return document, chart_result, table_result, build_context


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


def test_assemble_document_interleaves_markdown_and_artifacts_in_order(
    tmp_path: Path,
) -> None:
    document, chart_result, table_result, build_context = _chart_and_table_document(
        tmp_path
    )
    artifacts = [
        render_chart_artifact(chart_result, build_context),
        render_table_artifact(table_result, build_context),
    ]

    assembled = assemble_document(document, artifacts)

    assert assembled.source_path == document.source_path
    assert assembled.frontmatter == document.frontmatter
    assert [node.kind for node in assembled.nodes] == [
        NodeKind.MARKDOWN,
        NodeKind.RENDERED_ARTIFACT,
        NodeKind.MARKDOWN,
        NodeKind.RENDERED_ARTIFACT,
    ]
    assert isinstance(document.nodes[0], MarkdownNode)
    assert isinstance(document.nodes[2], MarkdownNode)
    assert assembled.nodes[0] == AssembledDocumentNode(
        kind=NodeKind.MARKDOWN,
        markdown=document.nodes[0],
    )
    assert assembled.nodes[1].artifact == artifacts[0]
    assert assembled.nodes[2] == AssembledDocumentNode(
        kind=NodeKind.MARKDOWN,
        markdown=document.nodes[2],
    )
    assert assembled.nodes[3].artifact == artifacts[1]


def test_assemble_document_raises_when_rendered_artifact_is_missing(
    tmp_path: Path,
) -> None:
    document, chart_result, _, build_context = _chart_and_table_document(tmp_path)
    artifacts = [render_chart_artifact(chart_result, build_context)]

    with pytest.raises(RenderingError) as exc_info:
        assemble_document(document, artifacts)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.message == "missing rendered artifact for executable block"
    assert diagnostic.block_id == "block-0002"
    assert diagnostic.block_type is BlockType.TABLE
    assert diagnostic.block_index == 1


def test_assemble_document_raises_for_duplicate_artifacts(tmp_path: Path) -> None:
    document, chart_result, _, build_context = _chart_and_table_document(tmp_path)
    artifact = render_chart_artifact(chart_result, build_context)

    with pytest.raises(RenderingError) as exc_info:
        assemble_document(document, [artifact, artifact])

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.message == "duplicate rendered artifact for executable block"
    assert diagnostic.block_id == chart_result.block.node_id


def test_assemble_document_raises_for_extra_artifact_not_in_document(
    tmp_path: Path,
) -> None:
    document, chart_result, _, build_context = _chart_and_table_document(tmp_path)
    artifact = render_chart_artifact(chart_result, build_context)
    extra_block = _block(
        source_path=document.source_path,
        index=2,
        block_type=BlockType.TABLE,
        code="orphan_frame",
    )
    extra_artifact = RenderedArtifact(
        artifact_id="table-block-9999",
        kind=ArtifactKind.TABLE,
        block=extra_block,
        path=build_context.table_path(2, ".html"),
        html="<table></table>",
        mime_type="text/html",
    )

    with pytest.raises(RenderingError) as exc_info:
        assemble_document(document, [artifact, extra_artifact])

    diagnostic = exc_info.value.diagnostic
    assert (
        diagnostic.message
        == "rendered artifact does not correspond to an executable block in the document"
    )
    assert diagnostic.block_id == extra_block.node_id


def test_assemble_document_raises_for_mismatched_artifact_block_metadata(
    tmp_path: Path,
) -> None:
    document, chart_result, _, build_context = _chart_and_table_document(tmp_path)
    artifact = render_chart_artifact(chart_result, build_context)
    mismatched_block = ExecutableBlockNode(
        node_id=chart_result.block.node_id,
        block_type=BlockType.TABLE,
        code=chart_result.block.code,
        block_index=chart_result.block.block_index,
        location=chart_result.block.location,
    )
    mismatched_artifact = artifact.model_copy(update={"block": mismatched_block})

    with pytest.raises(RenderingError) as exc_info:
        assemble_document(document, [mismatched_artifact])

    diagnostic = exc_info.value.diagnostic
    assert (
        diagnostic.message
        == "rendered artifact block metadata does not match parsed document block"
    )
    assert diagnostic.block_id == chart_result.block.node_id


def test_render_intermediate_document_renders_html_in_document_order(
    tmp_path: Path,
) -> None:
    document, chart_result, table_result, build_context = _chart_and_table_document(
        tmp_path
    )
    assembled = assemble_document(
        document,
        [
            render_chart_artifact(chart_result, build_context),
            render_table_artifact(table_result, build_context),
        ],
    )

    intermediate = render_intermediate_document(assembled)

    assert isinstance(intermediate, IntermediateDocument)
    assert intermediate.source_path == document.source_path
    assert intermediate.base_path == document.source_path.parent
    html = intermediate.html
    assert "<title>Report</title>" in html
    intro_index = html.index('data-node-id="node-0001"')
    chart_index = html.index('data-block-id="block-0001"')
    bridge_index = html.index('data-node-id="node-0002"')
    table_index = html.index('data-block-id="block-0002"')
    assert intro_index < chart_index < bridge_index < table_index
    assert "<h1>Report</h1>" in html
    assert "<h1>Intro</h1>" in html
    assert "<svg" in html
    assert "<table" in html
    assert "Bridge paragraph" in html


def test_render_intermediate_document_inserts_frontmatter_metadata(
    tmp_path: Path,
) -> None:
    document, chart_result, table_result, build_context = _chart_and_table_document(
        tmp_path
    )
    document.frontmatter = Frontmatter(
        title="Quarterly Review",
        author="Analyst",
        date="2026-03-06",
    )
    assembled = assemble_document(
        document,
        [
            render_chart_artifact(chart_result, build_context),
            render_table_artifact(table_result, build_context),
        ],
    )

    intermediate = render_intermediate_document(assembled)

    assert "<title>Quarterly Review</title>" in intermediate.html
    assert '<meta name="author" content="Analyst">' in intermediate.html
    assert '<meta name="date" content="2026-03-06">' in intermediate.html
    assert "<h1>Quarterly Review</h1>" in intermediate.html
    assert "<p>Analyst</p>" in intermediate.html
    assert "<p>2026-03-06</p>" in intermediate.html


def test_render_intermediate_document_raises_when_chart_svg_is_missing(
    tmp_path: Path,
) -> None:
    document, chart_result, table_result, build_context = _chart_and_table_document(
        tmp_path
    )
    chart_artifact = render_chart_artifact(chart_result, build_context)
    assert chart_artifact.path is not None
    chart_artifact.path.unlink()
    assembled = assemble_document(
        document,
        [chart_artifact, render_table_artifact(table_result, build_context)],
    )

    with pytest.raises(RenderingError) as exc_info:
        render_intermediate_document(assembled)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.message == "failed to read rendered chart artifact"
    assert diagnostic.block_id == chart_result.block.node_id
    assert diagnostic.block_type is BlockType.CHART


def test_render_intermediate_document_raises_when_table_html_is_missing(
    tmp_path: Path,
) -> None:
    document, chart_result, table_result, build_context = _chart_and_table_document(
        tmp_path
    )
    chart_artifact = render_chart_artifact(chart_result, build_context)
    table_artifact = render_table_artifact(table_result, build_context).model_copy(
        update={"html": None}
    )
    assembled = assemble_document(
        document,
        [chart_artifact, table_artifact],
    )

    with pytest.raises(RenderingError) as exc_info:
        render_intermediate_document(assembled)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.message == "table artifact is missing its rendered HTML fragment"
    assert diagnostic.block_id == table_result.block.node_id
    assert diagnostic.block_type is BlockType.TABLE


def test_render_intermediate_document_raises_for_template_render_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, chart_result, table_result, build_context = _chart_and_table_document(
        tmp_path
    )
    assembled = assemble_document(
        document,
        [
            render_chart_artifact(chart_result, build_context),
            render_table_artifact(table_result, build_context),
        ],
    )

    def _boom(frontmatter: Frontmatter | None, body_fragments: list[str]) -> str:
        raise RuntimeError("template failed")

    monkeypatch.setattr("mdcc.renderers.document._render_template", _boom)

    with pytest.raises(RenderingError) as exc_info:
        render_intermediate_document(assembled)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.message == "failed to render intermediate document template"
    assert diagnostic.source_path == document.source_path
    assert diagnostic.exception_type == "RuntimeError"
    assert diagnostic.exception_message == "template failed"
