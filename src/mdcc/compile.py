"""End-to-end compiler orchestrator."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
import typer

from mdcc.cache import CacheStore, load_dependency_hashes
from mdcc.executor import build_execution_payloads, run_payloads
from mdcc.models import ExecutionPayload, RenderedArtifact
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
    source_input = read_source_document(options.input_path)
    document = parse_document(source_input)
    assert_valid_document_structure(document)

    with BuildContext.create(
        document.source_path,
        keep=options.keep_build_dir,
    ) as build_context:
        payloads = build_execution_payloads(document, build_context)
        cache_store = CacheStore.for_source(document.source_path)
        artifacts = [
            _resolve_artifact(
                payload=payload,
                build_context=build_context,
                cache_store=cache_store,
                options=options,
            )
            for payload in payloads
        ]
        assembled = assemble_document(document, artifacts)
        intermediate = render_intermediate_document(assembled)
        return generate_pdf(intermediate, options.output_path)


def _resolve_artifact(
    *,
    payload: ExecutionPayload,
    build_context: BuildContext,
    cache_store: CacheStore,
    options: CompileOptions,
) -> RenderedArtifact:
    if not options.use_cache:
        _emit_cache_event(options, payload, "bypassed", "disabled via --no-cache")
        return _execute_and_render(
            payload=payload,
            build_context=build_context,
            cache_store=cache_store,
            timeout_seconds=options.timeout_seconds,
            persist_cache=False,
        )

    resolution = cache_store.resolve_artifact(
        payload=payload,
        build_context=build_context,
    )
    if resolution.artifact is not None:
        _emit_cache_event(options, payload, resolution.status, resolution.reason)
        return resolution.artifact

    _emit_cache_event(options, payload, resolution.status, resolution.reason)
    return _execute_and_render(
        payload=payload,
        build_context=build_context,
        cache_store=cache_store,
        timeout_seconds=options.timeout_seconds,
        persist_cache=True,
    )


def _execute_and_render(
    *,
    payload: ExecutionPayload,
    build_context: BuildContext,
    cache_store: CacheStore,
    timeout_seconds: float,
    persist_cache: bool,
) -> RenderedArtifact:
    execution_result = run_payloads([payload], timeout_seconds)[0]
    typed_result = assert_valid_typed_result(execution_result)
    artifact = render_typed_result(typed_result, build_context)
    if persist_cache:
        cache_store.store_typed_result(
            payload=payload,
            result=typed_result,
            artifact=artifact,
            dependencies=load_dependency_hashes(payload.dependency_path),
        )
    return artifact


def _emit_cache_event(
    options: CompileOptions,
    payload: ExecutionPayload,
    status: str,
    reason: str,
) -> None:
    if not options.verbose:
        return
    typer.echo(f"{payload.block.node_id}: cache {status} ({reason})")
