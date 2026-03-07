from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import mistune
from jinja2 import Environment, select_autoescape
from markupsafe import Markup, escape

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
from mdcc.references import (
    REFERENCE_PATTERN,
    ReferenceRegistry,
    build_reference_registry,
)

_MARKDOWN_RENDERER = mistune.create_markdown()
_MARKDOWN_AST_RENDERER = mistune.create_markdown(renderer="ast")
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
      .mdcc-caption {
        color: #374151;
        font-size: 10pt;
        line-height: 1.4;
      }
      .mdcc-caption--table {
        margin: 0 0 0.5rem;
      }
      .mdcc-caption--chart {
        margin: 0.5rem 0 0;
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
            or artifact.block.metadata != parsed_block.metadata
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
    reference_registry = _build_reference_registry(document)
    body_fragments: list[str] = []
    for node in document.nodes:
        try:
            body_fragments.append(_render_assembled_node(node, reference_registry))
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


def _render_assembled_node(
    node: AssembledDocumentNode,
    reference_registry: ReferenceRegistry,
) -> str:
    if node.markdown is not None:
        return _render_markdown_node(node.markdown, reference_registry)
    if node.artifact is not None:
        return _render_artifact(node.artifact, reference_registry)

    raise RenderingError.from_message(
        "assembled document node is missing renderable payload"
    )


def _render_markdown_node(
    node: MarkdownNode,
    reference_registry: ReferenceRegistry,
) -> str:
    try:
        tokens_result, state = _MARKDOWN_AST_RENDERER.parse(node.text)
        tokens = cast(list[dict[str, Any]], tokens_result)
        _replace_references_in_tokens(tokens, node, reference_registry)
        renderer = cast(mistune.HTMLRenderer, _MARKDOWN_RENDERER.renderer)
        html = renderer.render_tokens(tokens, state)
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


def _render_artifact(
    artifact: RenderedArtifact,
    reference_registry: ReferenceRegistry,
) -> str:
    if artifact.kind.value == "chart":
        return _render_chart_artifact_html(artifact, reference_registry)
    if artifact.kind.value == "table":
        return _render_table_artifact_html(artifact, reference_registry)

    raise RenderingError.from_message(
        "rendered artifact has unsupported kind for document rendering",
        context=_context_for_block(artifact.block),
        source_snippet=_source_snippet(artifact.block),
    )


def _render_chart_artifact_html(
    artifact: RenderedArtifact,
    reference_registry: ReferenceRegistry,
) -> str:
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

    caption = _render_caption_html(
        artifact, variant="chart", registry=reference_registry
    )
    return (
        f"<section {_artifact_attributes(artifact, 'mdcc-artifact mdcc-chart')}>"
        f"{svg}"
        f"{caption}"
        "</section>"
    )


def _render_table_artifact_html(
    artifact: RenderedArtifact,
    reference_registry: ReferenceRegistry,
) -> str:
    if artifact.html is None:
        raise RenderingError.from_message(
            "table artifact is missing its rendered HTML fragment",
            context=_context_for_block(artifact.block),
            source_snippet=_source_snippet(artifact.block),
        )

    caption = _render_caption_html(
        artifact, variant="table", registry=reference_registry
    )
    return (
        f"<section {_artifact_attributes(artifact, 'mdcc-artifact mdcc-table')}>"
        f"{caption}"
        f"{artifact.html}"
        "</section>"
    )


def _artifact_attributes(artifact: RenderedArtifact, class_name: str) -> str:
    attributes = [
        f'class="{escape(class_name)}"',
        f'data-block-id="{escape(artifact.block.node_id)}"',
    ]
    label = artifact.block.metadata.label
    if label is not None:
        escaped = escape(label)
        attributes.append(f'id="{escaped}"')
        attributes.append(f'data-label="{escaped}"')
    return " ".join(attributes)


def _render_caption_html(
    artifact: RenderedArtifact,
    *,
    variant: str,
    registry: ReferenceRegistry,
) -> str:
    caption = artifact.block.metadata.caption
    label = artifact.block.metadata.label
    prefix = registry[label].text if label is not None and label in registry else None

    if prefix is not None and caption is not None:
        rendered_caption = f"{prefix}. {caption}"
    elif prefix is not None:
        rendered_caption = prefix
    elif caption is not None:
        rendered_caption = caption
    else:
        return ""

    return (
        f'<p class="mdcc-caption mdcc-caption--{escape(variant)}">'
        f"{escape(rendered_caption)}"
        "</p>"
    )


def _build_reference_registry(document: AssembledDocument) -> ReferenceRegistry:
    blocks = [
        node.artifact.block for node in document.nodes if node.artifact is not None
    ]
    registry, duplicates = build_reference_registry(blocks)
    if duplicates:
        label, block = duplicates[0]
        raise RenderingError.from_message(
            f"duplicate label: {label}",
            context=_context_for_block(block),
            source_snippet=_source_snippet(block),
        )
    return registry


def _replace_references_in_tokens(
    tokens: list[dict[str, Any]],
    node: MarkdownNode,
    registry: ReferenceRegistry,
) -> None:
    for token in tokens:
        if token.get("type") == "text" and "raw" in token:
            token["raw"] = _replace_references_in_text(
                token["raw"],
                node,
                registry,
            )

        children = token.get("children")
        if isinstance(children, list):
            _replace_references_in_tokens(children, node, registry)


def _replace_references_in_text(
    text: str,
    node: MarkdownNode,
    registry: ReferenceRegistry,
) -> str:
    def replace(match) -> str:
        label = match.group("label")
        reference = registry.get(label)
        if reference is None:
            raise RenderingError.from_message(
                f"unresolved reference: {label}",
                context=ErrorContext(
                    source_path=node.location.source_path
                    if node.location is not None
                    else None,
                    location=node.location,
                ),
                source_snippet=node.location.snippet
                if node.location is not None
                else None,
            )
        return reference.text

    return REFERENCE_PATTERN.sub(replace, text)


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
