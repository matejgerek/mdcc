"""End-to-end compiler orchestrator."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from mdcc.executor import build_execution_payloads, run_payloads
from mdcc.models import BlockExecutionResult, TypedBlockResult
from mdcc.parser import parse_document
from mdcc.pdf import generate_pdf
from mdcc.reader import read_source_document
from mdcc.renderers import (
    assemble_document,
    render_intermediate_document,
    render_typed_result,
)
from mdcc.utils.workspace import BuildContext
from mdcc.validator import assert_valid_document_structure, assert_valid_typed_result


class CompileOptions(BaseModel):
    """Resolved compilation settings forwarded from the CLI."""

    input_path: Path
    output_path: Path
    timeout_seconds: float = Field(default=30.0, gt=0)
    keep_build_dir: bool = False
    verbose: bool = False


def compile(options: CompileOptions) -> Path:
    """Run the full compilation pipeline and return the output PDF path."""
    source_input = read_source_document(options.input_path)
    document = parse_document(source_input)
    assert_valid_document_structure(document)

    with BuildContext.create(
        document.source_path,
        keep=options.keep_build_dir,
    ) as build_context:
        payloads = build_execution_payloads(document, build_context)
        execution_results = run_payloads(payloads, options.timeout_seconds)
        typed_results = _validate_typed_results(execution_results)
        artifacts = [
            render_typed_result(result, build_context) for result in typed_results
        ]
        assembled = assemble_document(document, artifacts)
        intermediate = render_intermediate_document(assembled)
        return generate_pdf(intermediate, options.output_path)


def _validate_typed_results(
    execution_results: list[BlockExecutionResult],
) -> list[TypedBlockResult]:
    """Validate execution outputs in document order before rendering."""
    return [assert_valid_typed_result(result) for result in execution_results]
