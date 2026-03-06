from __future__ import annotations

from collections.abc import Sequence

from mdcc.errors import ErrorContext, RenderingError
from mdcc.models import (
    AssembledDocument,
    AssembledDocumentNode,
    DocumentModel,
    ExecutableBlockNode,
    MarkdownNode,
    NodeKind,
    RenderedArtifact,
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


__all__ = ["assemble_document"]
