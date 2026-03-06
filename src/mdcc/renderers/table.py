from __future__ import annotations

from mdcc.errors import ErrorContext, RenderingError
from mdcc.models import ArtifactKind, RenderedArtifact, TableResult
from mdcc.utils.workspace import BuildContext


def render_table_artifact(
    result: TableResult,
    build_context: BuildContext,
) -> RenderedArtifact:
    """Render a validated table result into a document-ready HTML artifact."""
    block = result.block
    target_path = build_context.table_path(block.block_index, ".html")

    try:
        html = result.value.to_html(index=True, escape=True)
        target_path.write_text(html, encoding="utf-8")
    except Exception as exc:
        raise RenderingError.from_exception(
            "failed to render table artifact",
            exc,
            context=_error_context(result),
            source_snippet=_source_snippet(result),
        ) from exc

    return RenderedArtifact(
        artifact_id=f"table-{block.node_id}",
        kind=ArtifactKind.TABLE,
        block=block,
        path=target_path,
        html=html,
        mime_type="text/html",
    )


def _error_context(result: TableResult) -> ErrorContext:
    block = result.block
    location = block.location
    return ErrorContext(
        source_path=location.source_path if location is not None else None,
        block_id=block.node_id,
        block_type=block.block_type,
        block_index=block.block_index,
        location=location,
    )


def _source_snippet(result: TableResult) -> str | None:
    location = result.block.location
    return location.snippet if location is not None else None


__all__ = ["render_table_artifact"]
