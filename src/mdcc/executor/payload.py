from __future__ import annotations

from mdcc.executor.prelude import build_runtime_prelude
from mdcc.models import DocumentModel, ExecutionPayload, ExecutableBlockNode
from mdcc.utils.workspace import BuildContext


def build_execution_payload(
    block: ExecutableBlockNode,
    build_context: BuildContext,
) -> ExecutionPayload:
    """Create and persist the execution script for a single block."""
    script_path = build_context.payload_path(block.block_index)
    result_path = build_context.result_path(block.block_index)
    log_path = build_context.log_path(block.block_index)
    execution_cwd = build_context.build_dir.parent
    script_text = _build_payload_script(block=block, result_path=result_path)
    script_path.write_text(script_text, encoding="utf-8")

    return ExecutionPayload(
        block=block,
        script_text=script_text,
        script_path=script_path,
        result_path=result_path,
        log_path=log_path,
        execution_cwd=execution_cwd,
    )


def build_execution_payloads(
    document: DocumentModel,
    build_context: BuildContext,
) -> list[ExecutionPayload]:
    """Create payloads for executable blocks in document order."""
    return [
        build_execution_payload(node, build_context)
        for node in document.nodes
        if isinstance(node, ExecutableBlockNode)
    ]


def _build_payload_script(*, block: ExecutableBlockNode, result_path) -> str:
    prelude = build_runtime_prelude(result_path)
    return f"{prelude}\n{block.code}"


__all__ = ["build_execution_payload", "build_execution_payloads"]
