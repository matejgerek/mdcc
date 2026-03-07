from __future__ import annotations

from pathlib import Path

from mdcc.models import (
    DocumentModel,
    ExecutableBlockNode,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)
from mdcc.parser import parse_document
from mdcc.reader import read_source_document
from mdcc.validator import validate_document_structure


def validate_source_file(
    input_path: Path,
) -> tuple[DocumentModel, ValidationResult[DocumentModel]]:
    source_input = read_source_document(input_path)
    document = parse_document(source_input)
    return document, validate_document_structure(document)


def format_validation_report(
    document: DocumentModel,
    result: ValidationResult[DocumentModel],
) -> str:
    warnings = [
        issue for issue in result.issues if issue.severity is ValidationSeverity.WARNING
    ]
    errors = [
        issue for issue in result.issues if issue.severity is ValidationSeverity.ERROR
    ]

    lines: list[str] = []
    if errors:
        lines.append("Validation failed")
        lines.append("")
        lines.append("Errors:")
        lines.extend(_format_issue_list(errors))
        if warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(_format_issue_list(warnings))
        return "\n".join(lines)

    lines.append("Validation successful")
    lines.append("")
    lines.append("Blocks discovered:")
    lines.extend(_format_blocks(document))
    lines.append("")
    lines.append("Labels:")
    lines.extend(_format_labels(document))
    if warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(_format_issue_list(warnings))
    return "\n".join(lines)


def _format_blocks(document: DocumentModel) -> list[str]:
    blocks = [node for node in document.nodes if isinstance(node, ExecutableBlockNode)]
    if not blocks:
        return ["- none"]

    lines: list[str] = []
    for display_index, block in enumerate(blocks, start=1):
        start_line = (
            block.location.span.start.line
            if block.location is not None and block.location.span is not None
            else "?"
        )
        lines.append(f"{display_index}. {block.block_type.value} (line {start_line})")
    return lines


def _format_labels(document: DocumentModel) -> list[str]:
    labels = [
        node.metadata.label
        for node in document.nodes
        if isinstance(node, ExecutableBlockNode) and node.metadata.label is not None
    ]
    if not labels:
        return ["- none"]
    return [f"- {label}" for label in labels]


def _format_issue_list(issues: list[ValidationIssue]) -> list[str]:
    return [f"- {_format_issue(issue)}" for issue in issues]


def _format_issue(issue: ValidationIssue) -> str:
    location = _format_location(issue)
    if location is None:
        return issue.message
    return f"{issue.message} ({location})"


def _format_location(issue: ValidationIssue) -> str | None:
    location = issue.location
    if location is None or location.span is None:
        return None

    start = location.span.start
    end = location.span.end
    if (start.line, start.column) == (end.line, end.column):
        return f"line {start.line}:{start.column}"
    if start.line == end.line:
        return f"line {start.line}:{start.column}-{end.column}"
    return f"lines {start.line}:{start.column}-{end.line}:{end.column}"


__all__ = ["format_validation_report", "validate_source_file"]
