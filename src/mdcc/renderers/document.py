from __future__ import annotations

from collections.abc import Sequence

import mistune
from jinja2 import Environment, select_autoescape
from markupsafe import Markup

from mdcc.errors import ErrorContext, RenderingError
from mdcc.models import (
    AssembledDocument,
    AssembledDocumentNode,
    DocumentModel,
    ExecutableBlockNode,
    Frontmatter,
    IntermediateDocument,
    MarkdownNode,
    NodeKind,
    RenderedArtifact,
)

_MARKDOWN_RENDERER = mistune.create_markdown()
_DOCUMENT_TEMPLATE = Environment(
    autoescape=select_autoescape(
        enabled_extensions=("html", "xml"),
        default_for_string=True,
    )
).from_string(
    """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>{{ title }}</title>
    {% if author %}<meta name="author" content="{{ author }}">{% endif %}
    {% if date %}<meta name="date" content="{{ date }}">{% endif %}
    <style>
      /* TODO: Revisit this as a minimal theming system so page margins and
         related layout spacing can be configured intentionally instead of
         living as hard-coded CSS defaults. */
      @page {
        margin: 8mm;
      }
      body {
        color: #111827;
        font-family: Georgia, "Times New Roman", serif;
        font-size: 12pt;
        line-height: 1.6;
      }
      .mdcc-frontmatter {
        border-bottom: 1px solid #d1d5db;
        margin-bottom: 2rem;
        padding-bottom: 1rem;
      }
      .mdcc-frontmatter h1 {
        font-size: 24pt;
        margin: 0 0 0.25rem;
      }
      .mdcc-frontmatter p {
        color: #4b5563;
        margin: 0.125rem 0;
      }
      .mdcc-markdown,
      .mdcc-artifact {
        margin-bottom: 1.5rem;
      }
      .mdcc-artifact table {
        border-collapse: collapse;
        width: 100%;
      }
      .mdcc-artifact th,
      .mdcc-artifact td {
        border: 1px solid #d1d5db;
        padding: 0.4rem 0.5rem;
        text-align: left;
      }
      .mdcc-artifact svg {
        display: block;
        height: auto;
        max-width: 100%;
      }
    </style>
  </head>
  <body>
    {% if show_frontmatter %}
    <header class="mdcc-frontmatter">
      {% if title %}<h1>{{ title }}</h1>{% endif %}
      {% if author %}<p>{{ author }}</p>{% endif %}
      {% if date %}<p>{{ date }}</p>{% endif %}
    </header>
    {% endif %}
    {{ body_html }}
  </body>
</html>
"""
)


def assemble_document(
    document: DocumentModel,
    artifacts: Sequence[RenderedArtifact],
) -> AssembledDocument:
    """Interleave markdown nodes with rendered artifacts in document order."""
    artifact_map = _index_artifacts_by_block_id(artifacts)
    executable_blocks = {
        node.node_id: node
        for node in document.nodes
        if isinstance(node, ExecutableBlockNode)
    }

    for artifact in artifacts:
        parsed_block = executable_blocks.get(artifact.block.node_id)
        if parsed_block is None:
            raise RenderingError.from_message(
                "rendered artifact does not correspond to an executable block in the document",
                context=_context_for_block(artifact.block),
                source_snippet=_source_snippet(artifact.block),
            )

        if (
            artifact.block.block_index != parsed_block.block_index
            or artifact.block.block_type is not parsed_block.block_type
        ):
            raise RenderingError.from_message(
                "rendered artifact block metadata does not match parsed document block",
                context=_context_for_block(parsed_block),
                source_snippet=_source_snippet(parsed_block),
            )

    assembled_nodes: list[AssembledDocumentNode] = []
    for node in document.nodes:
        if isinstance(node, MarkdownNode):
            assembled_nodes.append(
                AssembledDocumentNode(kind=NodeKind.MARKDOWN, markdown=node)
            )
            continue

        if node.node_id not in artifact_map:
            raise RenderingError.from_message(
                "missing rendered artifact for executable block",
                context=_context_for_block(node),
                source_snippet=_source_snippet(node),
            )
        artifact = artifact_map[node.node_id]

        assembled_nodes.append(
            AssembledDocumentNode(kind=NodeKind.RENDERED_ARTIFACT, artifact=artifact)
        )

    return AssembledDocument(
        source_path=document.source_path,
        frontmatter=document.frontmatter,
        nodes=assembled_nodes,
    )


def render_intermediate_document(document: AssembledDocument) -> IntermediateDocument:
    """Render an assembled document into the intermediate HTML form."""
    body_fragments: list[str] = []
    for node in document.nodes:
        try:
            body_fragments.append(_render_assembled_node(node))
        except RenderingError:
            raise
        except Exception as exc:
            raise RenderingError.from_exception(
                "failed to render assembled document node",
                exc,
                context=_context_for_assembled_node(node, document),
                source_snippet=_source_snippet_for_assembled_node(node),
            ) from exc

    try:
        html = _render_template(document.frontmatter, body_fragments)
    except Exception as exc:
        raise RenderingError.from_exception(
            "failed to render intermediate document template",
            exc,
            context=ErrorContext(source_path=document.source_path),
        ) from exc

    return IntermediateDocument(
        source_path=document.source_path,
        frontmatter=document.frontmatter,
        html=html,
        base_path=document.source_path.parent,
    )


def _index_artifacts_by_block_id(
    artifacts: Sequence[RenderedArtifact],
) -> dict[str, RenderedArtifact]:
    artifact_map: dict[str, RenderedArtifact] = {}
    for artifact in artifacts:
        block_id = artifact.block.node_id
        if block_id in artifact_map:
            raise RenderingError.from_message(
                "duplicate rendered artifact for executable block",
                context=_context_for_block(artifact.block),
                source_snippet=_source_snippet(artifact.block),
            )
        artifact_map[block_id] = artifact
    return artifact_map


def _context_for_block(block: ExecutableBlockNode) -> ErrorContext:
    location = block.location
    return ErrorContext(
        source_path=location.source_path if location is not None else None,
        block_id=block.node_id,
        block_type=block.block_type,
        block_index=block.block_index,
        location=location,
    )


def _source_snippet(block: ExecutableBlockNode) -> str | None:
    location = block.location
    return location.snippet if location is not None else None


def _render_assembled_node(node: AssembledDocumentNode) -> str:
    if node.markdown is not None:
        return _render_markdown_node(node.markdown)
    if node.artifact is not None:
        return _render_artifact(node.artifact)

    raise RenderingError.from_message(
        "assembled document node is missing renderable payload"
    )


def _render_markdown_node(node: MarkdownNode) -> str:
    try:
        html = _MARKDOWN_RENDERER(node.text)
    except Exception as exc:
        raise RenderingError.from_exception(
            "failed to render markdown node",
            exc,
            context=ErrorContext(
                source_path=node.location.source_path
                if node.location is not None
                else None,
                location=node.location,
            ),
            source_snippet=node.location.snippet if node.location is not None else None,
        ) from exc

    return (
        f'<section class="mdcc-markdown" data-node-id="{node.node_id}">{html}</section>'
    )


def _render_artifact(artifact: RenderedArtifact) -> str:
    if artifact.kind.value == "chart":
        return _render_chart_artifact_html(artifact)
    if artifact.kind.value == "table":
        return _render_table_artifact_html(artifact)

    raise RenderingError.from_message(
        "rendered artifact has unsupported kind for document rendering",
        context=_context_for_block(artifact.block),
        source_snippet=_source_snippet(artifact.block),
    )


def _render_chart_artifact_html(artifact: RenderedArtifact) -> str:
    if artifact.path is None:
        raise RenderingError.from_message(
            "chart artifact is missing its rendered SVG path",
            context=_context_for_block(artifact.block),
            source_snippet=_source_snippet(artifact.block),
        )

    try:
        svg = artifact.path.read_text(encoding="utf-8")
    except Exception as exc:
        raise RenderingError.from_exception(
            "failed to read rendered chart artifact",
            exc,
            context=_context_for_block(artifact.block),
            source_snippet=_source_snippet(artifact.block),
        ) from exc

    return (
        f'<section class="mdcc-artifact mdcc-chart" data-block-id="{artifact.block.node_id}">'
        f"{svg}"
        "</section>"
    )


def _render_table_artifact_html(artifact: RenderedArtifact) -> str:
    if artifact.html is None:
        raise RenderingError.from_message(
            "table artifact is missing its rendered HTML fragment",
            context=_context_for_block(artifact.block),
            source_snippet=_source_snippet(artifact.block),
        )

    return (
        f'<section class="mdcc-artifact mdcc-table" data-block-id="{artifact.block.node_id}">'
        f"{artifact.html}"
        "</section>"
    )


def _render_template(frontmatter: Frontmatter | None, body_fragments: list[str]) -> str:
    title = (
        frontmatter.title
        if frontmatter is not None and frontmatter.title
        else "mdcc document"
    )
    author = frontmatter.author if frontmatter is not None else None
    date = (
        str(frontmatter.date) if frontmatter is not None and frontmatter.date else None
    )
    show_frontmatter = any(
        value is not None
        for value in (
            frontmatter.title if frontmatter is not None else None,
            author,
            date,
        )
    )
    return _DOCUMENT_TEMPLATE.render(
        title=title,
        author=author,
        date=date,
        show_frontmatter=show_frontmatter,
        body_html=Markup("\n".join(body_fragments)),
    )


def _context_for_assembled_node(
    node: AssembledDocumentNode,
    document: AssembledDocument,
) -> ErrorContext:
    if node.artifact is not None:
        return _context_for_block(node.artifact.block)
    if node.markdown is not None:
        return ErrorContext(
            source_path=node.markdown.location.source_path
            if node.markdown.location is not None
            else document.source_path,
            location=node.markdown.location,
        )
    return ErrorContext(source_path=document.source_path)


def _source_snippet_for_assembled_node(node: AssembledDocumentNode) -> str | None:
    if node.artifact is not None:
        return _source_snippet(node.artifact.block)
    if node.markdown is not None and node.markdown.location is not None:
        return node.markdown.location.snippet
    return None


__all__ = ["assemble_document", "render_intermediate_document"]
