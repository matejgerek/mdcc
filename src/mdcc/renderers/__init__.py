from __future__ import annotations

from mdcc.models import ChartResult, RenderedArtifact, TableResult, TypedBlockResult
from mdcc.renderers.chart import render_chart_artifact
from mdcc.renderers.document import assemble_document, render_intermediate_document
from mdcc.renderers.table import render_table_artifact
from mdcc.utils.workspace import BuildContext


def render_typed_result(
    result: TypedBlockResult,
    build_context: BuildContext,
) -> RenderedArtifact:
    """Dispatch a validated typed result to the appropriate renderer."""
    if isinstance(result, ChartResult):
        return render_chart_artifact(result, build_context)
    if isinstance(result, TableResult):
        return render_table_artifact(result, build_context)

    msg = f"unsupported typed result for rendering: {type(result).__name__}"
    raise TypeError(msg)


__all__ = [
    "assemble_document",
    "render_chart_artifact",
    "render_intermediate_document",
    "render_table_artifact",
    "render_typed_result",
]
