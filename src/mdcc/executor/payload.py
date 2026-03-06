from __future__ import annotations

import ast
from pathlib import Path

from mdcc.errors import ErrorContext, ValidationError
from mdcc.executor.prelude import (
    build_no_expression_epilogue,
    build_result_epilogue,
    build_runtime_prelude,
)
from mdcc.models import (
    DocumentModel,
    ExecutionPayload,
    ExecutableBlockNode,
    SourceLocation,
    SourcePosition,
    SourceSpan,
)
from mdcc.utils.workspace import BuildContext


def build_execution_payload(
    block: ExecutableBlockNode,
    build_context: BuildContext,
) -> ExecutionPayload:
    """Create and persist the execution script for a single block."""
    _assert_runtime_policy(block)
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


# ──────────────────────────────────────────────────────────────────────
# Payload script assembly
# ──────────────────────────────────────────────────────────────────────


def _build_payload_script(*, block: ExecutableBlockNode, result_path: Path) -> str:
    """Assemble the full execution script: prelude + user code + epilogue."""
    prelude = build_runtime_prelude(result_path)
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


# ──────────────────────────────────────────────────────────────────────
# Runtime policy enforcement (T09)
# ──────────────────────────────────────────────────────────────────────


def _assert_runtime_policy(block: ExecutableBlockNode) -> None:
    try:
        tree = ast.parse(block.code)
    except SyntaxError as exc:
        raise ValidationError.from_exception(
            "executable block contains invalid Python syntax",
            exc,
            context=_build_error_context(
                block,
                location=_syntax_error_location(block, exc),
            ),
            source_snippet=_source_snippet_for_syntax_error(block, exc),
        ) from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            raise _policy_violation_error(
                block,
                node=node,
                message="user imports are not allowed in executable blocks",
            )

        if _is_dynamic_import_call(node):
            raise _policy_violation_error(
                block,
                node=node,
                message="dynamic imports are not allowed in executable blocks",
            )


def _is_dynamic_import_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name):
        return node.func.id == "__import__"
    if isinstance(node.func, ast.Attribute):
        return node.func.attr == "__import__"
    return False


def _policy_violation_error(
    block: ExecutableBlockNode,
    *,
    node: ast.AST,
    message: str,
) -> ValidationError:
    return ValidationError.from_message(
        message,
        context=_build_error_context(block, location=_node_location(block, node)),
        source_snippet=_source_snippet_for_node(block, node),
    )


def _build_error_context(
    block: ExecutableBlockNode,
    *,
    location: SourceLocation | None = None,
) -> ErrorContext:
    source_path = None
    if location is not None:
        source_path = location.source_path
    elif block.location is not None:
        source_path = block.location.source_path

    return ErrorContext(
        source_path=source_path,
        block_id=block.node_id,
        block_type=block.block_type,
        block_index=block.block_index,
        location=location or block.location,
    )


def _node_location(
    block: ExecutableBlockNode,
    node: ast.AST,
) -> SourceLocation | None:
    if block.location is None:
        return None

    start_line = getattr(node, "lineno", None)
    end_line = getattr(node, "end_lineno", None)
    start_col = getattr(node, "col_offset", None)
    end_col = getattr(node, "end_col_offset", None)
    base_line = _block_code_start_line(block)
    if (
        base_line is None
        or start_line is None
        or end_line is None
        or start_col is None
        or end_col is None
    ):
        return block.location

    return SourceLocation(
        source_path=block.location.source_path,
        span=SourceSpan(
            start=SourcePosition(line=base_line + start_line - 1, column=start_col + 1),
            end=SourcePosition(line=base_line + end_line - 1, column=max(1, end_col)),
        ),
        snippet=_source_snippet_for_node(block, node),
    )


def _syntax_error_location(
    block: ExecutableBlockNode,
    exc: SyntaxError,
) -> SourceLocation | None:
    if block.location is None or exc.lineno is None:
        return block.location

    base_line = _block_code_start_line(block)
    if base_line is None:
        return block.location

    column = max(1, (exc.offset or 1))
    return SourceLocation(
        source_path=block.location.source_path,
        span=SourceSpan(
            start=SourcePosition(line=base_line + exc.lineno - 1, column=column),
            end=SourcePosition(line=base_line + exc.lineno - 1, column=column),
        ),
        snippet=_source_snippet_for_syntax_error(block, exc),
    )


def _source_snippet_for_node(block: ExecutableBlockNode, node: ast.AST) -> str | None:
    lineno = getattr(node, "lineno", None)
    if lineno is None:
        return None

    lines = block.code.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return None


def _source_snippet_for_syntax_error(
    block: ExecutableBlockNode,
    exc: SyntaxError,
) -> str | None:
    if exc.lineno is None:
        return None

    lines = block.code.splitlines()
    if 1 <= exc.lineno <= len(lines):
        return lines[exc.lineno - 1]
    return exc.text.strip() if exc.text is not None else None


def _block_code_start_line(block: ExecutableBlockNode) -> int | None:
    if block.location is None or block.location.span is None:
        return None
    return block.location.span.start.line + 1


__all__ = ["build_execution_payload", "build_execution_payloads"]
