from __future__ import annotations

import vl_convert as vlc

from mdcc.errors import ErrorContext, RenderingError
from mdcc.models import ArtifactKind, ChartResult, RenderedArtifact
from mdcc.utils.workspace import BuildContext


def render_chart_artifact(
    result: ChartResult,
    build_context: BuildContext,
) -> RenderedArtifact:
    """Render a validated chart result into a document-ready SVG artifact."""
    block = result.block
    target_path = build_context.chart_path(block.block_index, ".svg")

    try:
        svg = vlc.vegalite_to_svg(result.spec)
        target_path.write_text(svg, encoding="utf-8")
    except Exception as exc:
        raise RenderingError.from_exception(
            "failed to render chart artifact",
            exc,
            context=_error_context(result),
            source_snippet=_source_snippet(result),
        ) from exc

    return RenderedArtifact(
        artifact_id=f"chart-{block.node_id}",
        kind=ArtifactKind.CHART,
        block=block,
        path=target_path,
        mime_type="image/svg+xml",
    )


def _error_context(result: ChartResult) -> ErrorContext:
    block = result.block
    location = block.location
    return ErrorContext(
        source_path=location.source_path if location is not None else None,
        block_id=block.node_id,
        block_type=block.block_type,
        block_index=block.block_index,
        location=location,
    )


def _source_snippet(result: ChartResult) -> str | None:
    location = result.block.location
    return location.snippet if location is not None else None


__all__ = ["render_chart_artifact"]
