from __future__ import annotations

import ast
from pathlib import Path

from mdcc.executor.prelude import (
    build_capture_mode,
    build_no_expression_epilogue,
    build_result_epilogue,
    build_runtime_prelude,
)
from mdcc.models import (
    DocumentModel,
    ExecutionPayload,
    ExecutableBlockNode,
)
from mdcc.utils.workspace import BuildContext
from mdcc.validator import assert_valid_executable_block_runtime_policy


def build_execution_payload(
    block: ExecutableBlockNode,
    build_context: BuildContext,
    *,
    capture_datasets: bool = False,
) -> ExecutionPayload:
    """Create and persist the execution script for a single block."""
    assert_valid_executable_block_runtime_policy(block)
    script_path = build_context.payload_path(block.block_index)
    result_path = build_context.result_path(block.block_index)
    dependency_path = build_context.dependency_path(block.block_index)
    dataset_manifest_path = build_context.dataset_manifest_path(block.block_index)
    dataset_payloads_dir = build_context.dataset_payload_dir(block.block_index)
    log_path = build_context.log_path(block.block_index)
    execution_cwd = build_context.build_dir.parent
    script_text = _build_payload_script(
        block=block,
        result_path=result_path,
        dependency_path=dependency_path,
        dataset_manifest_path=dataset_manifest_path,
        dataset_payloads_dir=dataset_payloads_dir,
        capture_datasets=capture_datasets,
    )
    script_path.write_text(script_text, encoding="utf-8")

    return ExecutionPayload(
        block=block,
        capture_datasets=capture_datasets,
        script_text=script_text,
        script_path=script_path,
        result_path=result_path,
        dependency_path=dependency_path,
        dataset_manifest_path=dataset_manifest_path,
        dataset_payloads_dir=dataset_payloads_dir,
        log_path=log_path,
        execution_cwd=execution_cwd,
    )


def build_execution_payloads(
    document: DocumentModel,
    build_context: BuildContext,
    *,
    capture_datasets: bool = False,
) -> list[ExecutionPayload]:
    """Create payloads for executable blocks in document order."""
    return [
        build_execution_payload(
            node,
            build_context,
            capture_datasets=capture_datasets,
        )
        for node in document.nodes
        if isinstance(node, ExecutableBlockNode)
    ]


# ──────────────────────────────────────────────────────────────────────
# Payload script assembly
# ──────────────────────────────────────────────────────────────────────


def _build_payload_script(
    *,
    block: ExecutableBlockNode,
    result_path: Path,
    dependency_path: Path,
    dataset_manifest_path: Path,
    dataset_payloads_dir: Path,
    capture_datasets: bool,
) -> str:
    """Assemble the full execution script: prelude + user code + epilogue."""
    prelude = build_runtime_prelude(
        result_path,
        dependency_path,
        dataset_manifest_path,
        dataset_payloads_dir,
        capture_datasets=capture_datasets,
    )
    user_code, epilogue = _rewrite_last_expression(block.code)
    return f"{prelude}\n{user_code}\n{epilogue}"


def _rewrite_last_expression(source: str) -> tuple[str, str]:
    """Split user code into body + result-capture epilogue.

    If the last statement in *source* is an ``ast.Expr`` (a bare
    expression), the expression source is extracted and the epilogue
    will serialise its value to ``MDCC_RESULT_PATH``.

    If the last statement is *not* an expression (assignment, for-loop,
    etc.), the entire source is returned unchanged and the epilogue
    records ``has_value = False``.

    Returns
    -------
    tuple[str, str]
        ``(possibly_modified_user_code, epilogue_source)``
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Syntax errors are caught separately by policy validation;
        # just return the code as-is so the subprocess reports the error.
        return source, build_no_expression_epilogue()

    if not tree.body:
        return source, build_no_expression_epilogue()

    last_stmt = tree.body[-1]

    if not isinstance(last_stmt, ast.Expr):
        # Last statement is not an expression — nothing to capture.
        return source, build_no_expression_epilogue()

    # Extract the source text of the final expression.
    expr_source = _extract_expression_source(source, last_stmt)

    # Build body = everything *before* the last expression statement.
    body_source = _source_before_node(source, last_stmt)

    epilogue = build_result_epilogue(expr_source)
    return body_source, epilogue


def capture_mode_for_source(source: str) -> str:
    """Return the stable capture mode used for cache fingerprinting."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return build_capture_mode(False)

    if not tree.body:
        return build_capture_mode(False)

    return build_capture_mode(isinstance(tree.body[-1], ast.Expr))


def _extract_expression_source(full_source: str, node: ast.Expr) -> str:
    """Return the raw source text corresponding to an ``ast.Expr`` node."""
    return ast.get_source_segment(full_source, node.value) or ast.unparse(node.value)


def _source_before_node(full_source: str, node: ast.AST) -> str:
    """Return all source text *before* the given AST node.

    Uses column-aware slicing so that preceding statements on the
    same physical line (e.g. ``x = 1; y = 2; x + y``) are preserved.
    """
    lineno = getattr(node, "lineno", None)
    col_offset = getattr(node, "col_offset", None)
    if lineno is None:
        return ""

    lines = full_source.splitlines(keepends=True)

    if lineno == 1 and (col_offset is None or col_offset == 0):
        return ""

    # Everything on lines strictly before the node's line …
    before = "".join(lines[: lineno - 1])

    # … plus any text on the same line up to the column offset.
    if col_offset is not None and col_offset > 0 and lineno <= len(lines):
        same_line_prefix = lines[lineno - 1][:col_offset]
        before += same_line_prefix

    return before


__all__ = [
    "build_execution_payload",
    "build_execution_payloads",
    "capture_mode_for_source",
]
