from __future__ import annotations

from collections.abc import Iterable

from mdcc.errors import ValidationError
from mdcc.models import (
    BlockType,
    Diagnostic,
    DiagnosticCategory,
    DiagnosticStage,
    DocumentModel,
    ExecutableBlockNode,
    Frontmatter,
    MarkdownNode,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)


def validate_document_structure(document: DocumentModel) -> ValidationResult[DocumentModel]:
    issues: list[ValidationIssue] = []
    issues.extend(_validate_frontmatter(document.frontmatter, document.source_path))
    issues.extend(_validate_nodes(document))

    return ValidationResult(
        ok=not any(issue.severity is ValidationSeverity.ERROR for issue in issues),
        value=document if not any(issue.severity is ValidationSeverity.ERROR for issue in issues) else None,
        issues=issues,
    )


def assert_valid_document_structure(document: DocumentModel) -> DocumentModel:
    result = validate_document_structure(document)
    if result.ok:
        return document

    raise ValidationError(_build_validation_diagnostic(document, result.issues))


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
        first_block = next((node for node in nodes if isinstance(node, ExecutableBlockNode)), None)
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


def _build_validation_diagnostic(
    document: DocumentModel,
    issues: list[ValidationIssue],
) -> Diagnostic:
    error_issues = [issue for issue in issues if issue.severity is ValidationSeverity.ERROR]
    primary_issue = error_issues[0] if error_issues else issues[0]
    return Diagnostic(
        stage=DiagnosticStage.VALIDATION,
        category=DiagnosticCategory.VALIDATION_ERROR,
        message=primary_issue.message,
        source_path=document.source_path,
        location=primary_issue.location,
        exception_message=_format_issue_summary(issues),
    )


def _format_issue_summary(issues: list[ValidationIssue]) -> str:
    return "; ".join(f"{issue.code}: {issue.message}" for issue in issues)


__all__ = ["assert_valid_document_structure", "validate_document_structure"]
