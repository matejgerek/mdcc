from __future__ import annotations

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
    TableResult,
    TypedBlockResult,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)

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
        executable_indices.append(node.block_index)

    issues.extend(_validate_executable_indices(document.nodes, executable_indices))
    return issues


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


def _build_validation_error(
    document: DocumentModel,
    issues: list[ValidationIssue],
) -> ValidationError:
    error_issues = [
        issue for issue in issues if issue.severity is ValidationSeverity.ERROR
    ]
    primary_issue = error_issues[0] if error_issues else issues[0]
    return ValidationError.from_message(
        primary_issue.message,
        context=ErrorContext(
            source_path=document.source_path,
            location=primary_issue.location,
        ),
        exception_message=_format_issue_summary(issues),
    )


def _format_issue_summary(issues: list[ValidationIssue]) -> str:
    return "; ".join(f"{issue.code}: {issue.message}" for issue in issues)


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


__all__ = [
    "assert_valid_document_structure",
    "assert_valid_typed_result",
    "validate_document_structure",
    "validate_typed_result",
]
