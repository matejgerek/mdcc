"""End-to-end compiler orchestrator."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
import typer

from mdcc.cache import CacheStore, load_dependency_hashes
from mdcc.executor import (
    build_execution_payloads,
    read_runtime_dataset_captures,
    run_payloads,
)
from mdcc.models import (
    CompiledBlockRecord,
    DocumentModel,
    ExecutionPayload,
)
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
    use_cache: bool = True
    verbose: bool = False


def compile(options: CompileOptions) -> Path:
    """Run the full compilation pipeline and return the output PDF path."""
    document = load_document_model(options.input_path)

    with BuildContext.create(
        document.source_path,
        keep=options.keep_build_dir,
    ) as build_context:
        compiled_blocks = materialize_compiled_blocks(
            document=document,
            build_context=build_context,
            timeout_seconds=options.timeout_seconds,
            use_cache=options.use_cache,
            capture_datasets=False,
            verbose=options.verbose,
        )
        artifacts = [
            record.rendered_artifact
            for record in compiled_blocks
            if record.rendered_artifact is not None
        ]
        assembled = assemble_document(document, artifacts)
        intermediate = render_intermediate_document(assembled)
        return generate_pdf(intermediate, options.output_path)


def load_document_model(input_path: Path) -> DocumentModel:
    """Read, parse, and structurally validate a source document."""
    source_input = read_source_document(input_path)
    document = parse_document(source_input)
    assert_valid_document_structure(document)
    return document


def materialize_compiled_blocks(
    *,
    document: DocumentModel,
    build_context: BuildContext,
    timeout_seconds: float,
    use_cache: bool,
    capture_datasets: bool,
    verbose: bool,
) -> list[CompiledBlockRecord]:
    """Materialize executable blocks into compiled block records."""
    payloads = build_execution_payloads(
        document,
        build_context,
        capture_datasets=capture_datasets,
    )
    cache_store = CacheStore.for_source(document.source_path)
    records = [
        _resolve_compiled_block(
            payload=payload,
            build_context=build_context,
            cache_store=cache_store,
            timeout_seconds=timeout_seconds,
            use_cache=use_cache,
            verbose=verbose,
        )
        for payload in payloads
    ]
    return records


def _resolve_compiled_block(
    *,
    payload: ExecutionPayload,
    build_context: BuildContext,
    cache_store: CacheStore,
    timeout_seconds: float,
    use_cache: bool,
    verbose: bool,
) -> CompiledBlockRecord:
    if not use_cache:
        _emit_cache_event(verbose, payload, "bypassed", "disabled via --no-cache")
        return _execute_and_render(
            payload=payload,
            build_context=build_context,
            cache_store=cache_store,
            timeout_seconds=timeout_seconds,
            persist_cache=False,
        )

    resolution = cache_store.resolve_compiled_record(
        payload=payload,
        build_context=build_context,
    )
    if resolution.compiled_record is not None:
        _emit_cache_event(verbose, payload, resolution.status, resolution.reason)
        return resolution.compiled_record

    _emit_cache_event(verbose, payload, resolution.status, resolution.reason)
    return _execute_and_render(
        payload=payload,
        build_context=build_context,
        cache_store=cache_store,
        timeout_seconds=timeout_seconds,
        persist_cache=True,
    )


def _execute_and_render(
    *,
    payload: ExecutionPayload,
    build_context: BuildContext,
    cache_store: CacheStore,
    timeout_seconds: float,
    persist_cache: bool,
) -> CompiledBlockRecord:
    execution_result = run_payloads([payload], timeout_seconds)[0]
    typed_result = assert_valid_typed_result(execution_result)
    dataset_captures = read_runtime_dataset_captures(payload.dataset_manifest_path)
    artifact = render_typed_result(typed_result, build_context)
    dependencies = load_dependency_hashes(payload.dependency_path)
    if persist_cache:
        cache_store.store_typed_result(
            payload=payload,
            execution_result=execution_result,
            result=typed_result,
            artifact=artifact,
            dependencies=dependencies,
            dataset_captures=dataset_captures,
        )
    return CompiledBlockRecord(
        payload=payload,
        execution_result=execution_result,
        typed_result=typed_result,
        dependencies=dependencies,
        dataset_captures=dataset_captures,
        rendered_artifact=artifact,
    )


def _emit_cache_event(
    verbose: bool,
    payload: ExecutionPayload,
    status: str,
    reason: str,
) -> None:
    if not verbose:
        return
    typer.echo(f"{payload.block.node_id}: cache {status} ({reason})")
