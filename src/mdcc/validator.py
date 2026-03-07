from __future__ import annotations

import ast
from collections.abc import Iterable
import re

import altair as alt
import pandas as pd

from mdcc.errors import ErrorContext, ValidationError
from mdcc.models import (
    BlockType,
    BlockExecutionResult,
    BlockMetadata,
    ChartResult,
    DocumentModel,
    ExecutableBlockNode,
    Frontmatter,
    MarkdownNode,
    SourceLocation,
    SourcePosition,
    SourceSpan,
    TableResult,
    TypedBlockResult,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)
from mdcc.references import build_reference_registry, iter_reference_labels_in_markdown

_SUPPORTED_CHART_TYPES = (
    alt.Chart,
    alt.LayerChart,
    alt.ConcatChart,
    alt.HConcatChart,
    alt.VConcatChart,
)
_SUPPORTED_BLOCK_METADATA_KEYS = frozenset({"caption", "label"})
_LABEL_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9:_-]*$")


def validate_document_structure(
    document: DocumentModel,
) -> ValidationResult[DocumentModel]:
    issues: list[ValidationIssue] = []
    issues.extend(_validate_frontmatter(document.frontmatter, document.source_path))
    issues.extend(_validate_nodes(document))

    return ValidationResult(
        ok=not any(issue.severity is ValidationSeverity.ERROR for issue in issues),
        value=document
        if not any(issue.severity is ValidationSeverity.ERROR for issue in issues)
        else None,
        issues=issues,
    )


def assert_valid_document_structure(document: DocumentModel) -> DocumentModel:
    result = validate_document_structure(document)
    if result.ok:
        return document

    raise _build_validation_error(document, result.issues)


def validate_typed_result(
    result: BlockExecutionResult,
) -> ValidationResult[TypedBlockResult]:
    issue = _typed_result_issue(result)
    if issue is not None:
        return ValidationResult(ok=False, issues=[issue])

    return ValidationResult(ok=True, value=_coerce_typed_result(result))


def assert_valid_typed_result(result: BlockExecutionResult) -> TypedBlockResult:
    validation = validate_typed_result(result)
    if validation.ok and validation.value is not None:
        return validation.value

    raise _build_typed_result_validation_error(
        result,
        validation.issues[0],
    )


def _validate_frontmatter(
    frontmatter: Frontmatter | None,
    source_path,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if frontmatter is None:
        return issues

    if not isinstance(frontmatter, Frontmatter):
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="frontmatter-invalid-type",
                message="frontmatter must be a Frontmatter model or None",
            )
        )
        return issues

    if frontmatter.title is not None and not isinstance(frontmatter.title, str):
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="frontmatter-title-invalid",
                message="frontmatter title must be a string when present",
            )
        )

    if frontmatter.author is not None and not isinstance(frontmatter.author, str):
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="frontmatter-author-invalid",
                message="frontmatter author must be a string when present",
            )
        )

    if frontmatter.extra:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                code="frontmatter-extra-preserved",
                message="unknown frontmatter fields were preserved in extra",
            )
        )

    return issues


def _validate_nodes(document: DocumentModel) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen_node_ids: set[str] = set()
    executable_indices: list[int] = []
    executable_blocks: list[ExecutableBlockNode] = []
    markdown_nodes: list[MarkdownNode] = []

    for index, node in enumerate(document.nodes):
        if not isinstance(node, MarkdownNode | ExecutableBlockNode):
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="node-unsupported-type",
                    message=f"unsupported document node type at position {index}",
                )
            )
            continue

        if node.node_id in seen_node_ids:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="node-id-duplicate",
                    message=f"duplicate node id detected: {node.node_id}",
                    location=node.location,
                )
            )
        else:
            seen_node_ids.add(node.node_id)

        if node.location is None:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="node-location-missing",
                    message=f"node {node.node_id} is missing source location metadata",
                )
            )
        elif node.location.source_path != document.source_path:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="node-location-path-mismatch",
                    message=f"node {node.node_id} location path does not match document source path",
                    location=node.location,
                )
            )

        if isinstance(node, MarkdownNode):
            markdown_nodes.append(node)
            if node.text == "":
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code="markdown-empty",
                        message=f"markdown node {node.node_id} must not be empty",
                        location=node.location,
                    )
                )
            continue

        if node.block_type not in set(BlockType):
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="block-type-unknown",
                    message=f"unknown executable block type: {node.block_type}",
                    location=node.location,
                )
            )

        issues.extend(_validate_block_metadata(node))
        issues.extend(validate_executable_block_runtime_policy(node))
        executable_indices.append(node.block_index)
        executable_blocks.append(node)

    issues.extend(_validate_executable_indices(document.nodes, executable_indices))
    issues.extend(_validate_reference_labels(executable_blocks))
    issues.extend(_validate_markdown_references(markdown_nodes, executable_blocks))
    return issues


def validate_executable_block_runtime_policy(
    block: ExecutableBlockNode,
) -> list[ValidationIssue]:
    try:
        tree = ast.parse(block.code)
    except SyntaxError as exc:
        return [
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="block-code-syntax-invalid",
                message="executable block contains invalid Python syntax",
                location=_syntax_error_location(block, exc),
            )
        ]

    issues: list[ValidationIssue] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="block-import-disallowed",
                    message="user imports are not allowed in executable blocks",
                    location=_node_location(block, node),
                )
            )

        if _is_dynamic_import_call(node):
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="block-dynamic-import-disallowed",
                    message="dynamic imports are not allowed in executable blocks",
                    location=_node_location(block, node),
                )
            )

    return issues


def assert_valid_executable_block_runtime_policy(
    block: ExecutableBlockNode,
) -> None:
    issues = validate_executable_block_runtime_policy(block)
    if not issues:
        return

    primary_issue = issues[0]
    raise ValidationError.from_message(
        primary_issue.message,
        context=ErrorContext(
            source_path=primary_issue.location.source_path
            if primary_issue.location is not None
            else (block.location.source_path if block.location is not None else None),
            block_id=block.node_id,
            block_type=block.block_type,
            block_index=block.block_index,
            location=primary_issue.location or block.location,
        ),
        source_snippet=(
            primary_issue.location.snippet
            if primary_issue.location is not None
            else (block.location.snippet if block.location is not None else None)
        ),
        exception_message=primary_issue.code,
    )


def _validate_executable_indices(
    nodes: Iterable[MarkdownNode | ExecutableBlockNode],
    executable_indices: list[int],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    expected_indices = list(range(len(executable_indices)))

    if executable_indices != expected_indices:
        first_block = next(
            (node for node in nodes if isinstance(node, ExecutableBlockNode)), None
        )
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="block-index-sequence-invalid",
                message=(
                    "executable block indices must be contiguous and zero-based in document order"
                ),
                location=first_block.location if first_block is not None else None,
            )
        )

    return issues


def _validate_block_metadata(node: ExecutableBlockNode) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    normalized: dict[str, str] = {}
    seen_keys: set[str] = set()

    for key, value in node.raw_metadata:
        if key in seen_keys:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="block-metadata-key-duplicate",
                    message=f"duplicate metadata key '{key}'",
                    location=node.location,
                )
            )
            continue

        seen_keys.add(key)

        if key not in _SUPPORTED_BLOCK_METADATA_KEYS:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="block-metadata-key-unknown",
                    message=(
                        f"unsupported metadata key '{key}' for {node.block_type.value} "
                        "in this compiler version"
                    ),
                    location=node.location,
                )
            )
            continue

        normalized[key] = value.strip()

    caption = normalized.get("caption")
    if caption is not None and caption == "":
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="block-metadata-caption-empty",
                message="caption must not be empty",
                location=node.location,
            )
        )

    label = normalized.get("label")
    if label is not None and not _LABEL_PATTERN.fullmatch(label):
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="block-metadata-label-invalid",
                message=(
                    f"invalid label '{label}'; expected pattern "
                    r"^[A-Za-z][A-Za-z0-9:_-]*$"
                ),
                location=node.location,
            )
        )

    if not any(issue.severity is ValidationSeverity.ERROR for issue in issues):
        node.metadata = BlockMetadata(
            caption=caption,
            label=label,
        )

    return issues


def _validate_reference_labels(
    executable_blocks: list[ExecutableBlockNode],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    _, duplicates = build_reference_registry(executable_blocks)

    for label, block in duplicates:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="block-label-duplicate",
                message=f"duplicate label: {label}",
                location=block.location,
            )
        )

    return issues


def _validate_markdown_references(
    markdown_nodes: list[MarkdownNode],
    executable_blocks: list[ExecutableBlockNode],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    registry, _ = build_reference_registry(executable_blocks)

    for node in markdown_nodes:
        for label in iter_reference_labels_in_markdown(node.text):
            if label not in registry:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code="markdown-reference-unresolved",
                        message=f"unresolved reference: {label}",
                        location=node.location,
                    )
                )

    return issues


def _build_validation_error(
    document: DocumentModel,
    issues: list[ValidationIssue],
) -> ValidationError:
    error_issues = [
        issue for issue in issues if issue.severity is ValidationSeverity.ERROR
    ]
    primary_issue = error_issues[0] if error_issues else issues[0]
    matching_block = _find_executable_block_for_issue(document, primary_issue)
    return ValidationError.from_message(
        primary_issue.message,
        context=ErrorContext(
            source_path=primary_issue.location.source_path
            if primary_issue.location is not None
            else document.source_path,
            block_id=matching_block.node_id if matching_block is not None else None,
            block_type=matching_block.block_type
            if matching_block is not None
            else None,
            block_index=matching_block.block_index
            if matching_block is not None
            else None,
            location=primary_issue.location,
        ),
        source_snippet=primary_issue.location.snippet
        if primary_issue.location is not None
        else None,
        exception_message=_format_issue_summary(issues),
    )


def _format_issue_summary(issues: list[ValidationIssue]) -> str:
    return "; ".join(f"{issue.code}: {issue.message}" for issue in issues)


def _find_executable_block_for_issue(
    document: DocumentModel,
    issue: ValidationIssue,
) -> ExecutableBlockNode | None:
    if issue.location is None or issue.location.span is None:
        return None

    issue_start = issue.location.span.start
    issue_end = issue.location.span.end

    for node in document.nodes:
        if not isinstance(node, ExecutableBlockNode):
            continue
        if node.location is None or node.location.span is None:
            continue
        if node.location.source_path != issue.location.source_path:
            continue

        block_start = node.location.span.start
        block_end = node.location.span.end
        if (block_start.line, block_start.column) <= (
            issue_start.line,
            issue_start.column,
        ) and (issue_end.line, issue_end.column) <= (block_end.line, block_end.column):
            return node

    return None


def _typed_result_issue(result: BlockExecutionResult) -> ValidationIssue | None:
    if result.block.block_type is BlockType.CHART:
        if isinstance(result.raw_value, _SUPPORTED_CHART_TYPES):
            return None
        return _build_typed_result_issue(
            result,
            code="chart-output-missing"
            if _is_missing_final_expression(result)
            else "chart-output-invalid-type",
            message="chart block must return an Altair chart object",
        )

    if result.block.block_type is BlockType.TABLE:
        if isinstance(result.raw_value, pd.DataFrame):
            return None
        return _build_typed_result_issue(
            result,
            code="table-output-missing"
            if _is_missing_final_expression(result)
            else "table-output-invalid-type",
            message="table block must return a pandas DataFrame",
        )

    return _build_typed_result_issue(
        result,
        code="block-output-invalid-type",
        message="executable block returned an unsupported output type",
    )


def _build_typed_result_issue(
    result: BlockExecutionResult,
    *,
    code: str,
    message: str,
) -> ValidationIssue:
    return ValidationIssue(
        severity=ValidationSeverity.ERROR,
        code=code,
        message=message,
        location=result.block.location,
    )


def _coerce_typed_result(result: BlockExecutionResult) -> TypedBlockResult:
    if result.block.block_type is BlockType.CHART:
        chart = result.raw_value
        if not isinstance(chart, _SUPPORTED_CHART_TYPES):
            msg = "chart output must be validated before coercion"
            raise TypeError(msg)
        return ChartResult(block=result.block, value=chart, spec=chart.to_dict())

    table = result.raw_value
    if not isinstance(table, pd.DataFrame):
        msg = "table output must be validated before coercion"
        raise TypeError(msg)
    return TableResult(block=result.block, value=table)


def _build_typed_result_validation_error(
    result: BlockExecutionResult,
    issue: ValidationIssue,
) -> ValidationError:
    return ValidationError.from_message(
        issue.message,
        context=ErrorContext(
            source_path=result.block.location.source_path
            if result.block.location is not None
            else None,
            block_id=result.block.node_id,
            block_type=result.block.block_type,
            block_index=result.block.block_index,
            location=issue.location,
        ),
        source_snippet=result.block.location.snippet
        if result.block.location is not None
        else None,
        stdout=result.streams.stdout,
        stderr=result.streams.stderr,
        duration_ms=result.timing.duration_ms,
        expected_output_type=_expected_output_type(result.block.block_type),
        actual_output_type=_actual_output_type(result),
        exception_message=issue.code,
    )


def _expected_output_type(block_type: BlockType) -> str:
    if block_type is BlockType.CHART:
        return "Altair chart object"
    if block_type is BlockType.TABLE:
        return "pandas.DataFrame"
    return "supported executable block output"


def _actual_output_type(result: BlockExecutionResult) -> str:
    if result.raw_type_name is not None:
        return result.raw_type_name
    if result.raw_value is not None:
        value_type = type(result.raw_value)
        return f"{value_type.__module__}.{value_type.__name__}"
    return "missing final expression"


def _is_missing_final_expression(result: BlockExecutionResult) -> bool:
    return result.raw_value is None and result.raw_type_name is None


def _is_dynamic_import_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name):
        return node.func.id == "__import__"
    if isinstance(node.func, ast.Attribute):
        return node.func.attr == "__import__"
    return False


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
            start=SourcePosition(
                line=base_line + start_line - 1,
                column=start_col + 1,
            ),
            end=SourcePosition(
                line=base_line + end_line - 1,
                column=max(1, end_col),
            ),
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

    column = max(1, exc.offset or 1)
    return SourceLocation(
        source_path=block.location.source_path,
        span=SourceSpan(
            start=SourcePosition(
                line=base_line + exc.lineno - 1,
                column=column,
            ),
            end=SourcePosition(
                line=base_line + exc.lineno - 1,
                column=column,
            ),
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


__all__ = [
    "assert_valid_document_structure",
    "assert_valid_executable_block_runtime_policy",
    "assert_valid_typed_result",
    "validate_document_structure",
    "validate_executable_block_runtime_policy",
    "validate_typed_result",
]
