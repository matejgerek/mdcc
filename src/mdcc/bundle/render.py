from __future__ import annotations

from pathlib import Path

from mdcc.bundle.outputs import output_parquet_bytes_to_frame, vega_json_bytes_to_spec
from mdcc.bundle.store import list_tables
from mdcc.bundle.validate import validate_bundle
from mdcc.errors import BundleError, ErrorContext
from mdcc.models import (
    BundleBlockOutputRecord,
    BundleModel,
    BundleOutputFormat,
    BundleOutputKind,
    DocumentModel,
    ExecutableBlockNode,
    RenderedArtifact,
    SourceDocumentInput,
)
from mdcc.parser import parse_document
from mdcc.pdf import generate_pdf
from mdcc.reader import extract_frontmatter, parse_frontmatter
from mdcc.renderers import (
    assemble_document,
    render_chart_spec_artifact,
    render_intermediate_document,
    render_table_frame_artifact,
)
from mdcc.utils.workspace import BuildContext
from mdcc.validator import assert_valid_document_structure

_RENDER_OUTPUT_TABLES = frozenset({"block_outputs", "output_payloads"})


def render_bundle(bundle_path: Path, output_path: Path) -> Path:
    bundle = validate_bundle(bundle_path)
    document = _parse_bundle_document(bundle_path, bundle)

    with BuildContext.create(bundle_path) as build_context:
        artifacts = _render_bundle_artifacts(
            bundle_path, bundle, document, build_context
        )
        assembled = assemble_document(document, artifacts)
        intermediate = render_intermediate_document(assembled)
        return generate_pdf(intermediate, output_path)


def _parse_bundle_document(bundle_path: Path, bundle: BundleModel) -> DocumentModel:
    source_text = bundle.document.source_text
    frontmatter_text, body_text = extract_frontmatter(source_text, bundle_path)
    frontmatter = parse_frontmatter(frontmatter_text, bundle_path)
    document = parse_document(
        SourceDocumentInput(
            source_path=bundle_path,
            raw_text=source_text,
            body_text=body_text,
            frontmatter_text=frontmatter_text,
            frontmatter=frontmatter,
        )
    )
    assert_valid_document_structure(document)
    return document


def _render_bundle_artifacts(
    bundle_path: Path,
    bundle: BundleModel,
    document: DocumentModel,
    build_context: BuildContext,
) -> list[RenderedArtifact]:
    executable_blocks = [
        node for node in document.nodes if isinstance(node, ExecutableBlockNode)
    ]
    if not executable_blocks:
        return []

    tables = list_tables(bundle_path)
    if not _RENDER_OUTPUT_TABLES.issubset(tables):
        raise BundleError.from_message(
            "bundle does not include persisted render outputs; recreate it with bundle render support",
            context=ErrorContext(source_path=bundle_path),
        )

    outputs_by_block = _index_outputs_by_block_id(bundle, bundle_path)
    payloads_by_id = {payload.payload_id: payload for payload in bundle.output_payloads}

    artifacts: list[RenderedArtifact] = []
    for block in executable_blocks:
        output = outputs_by_block.get(block.node_id)
        if output is None:
            raise BundleError.from_message(
                f"bundle is missing persisted render output for block '{block.node_id}'",
                context=ErrorContext(
                    source_path=bundle_path,
                    block_id=block.node_id,
                    block_type=block.block_type,
                    block_index=block.block_index,
                    location=block.location,
                ),
            )
        payload = payloads_by_id.get(output.payload_id)
        if payload is None:
            raise BundleError.from_message(
                f"bundle render output for block '{block.node_id}' references missing payload '{output.payload_id}'",
                context=ErrorContext(
                    source_path=bundle_path,
                    block_id=block.node_id,
                    block_type=block.block_type,
                    block_index=block.block_index,
                    location=block.location,
                ),
            )
        artifacts.append(
            _render_output_payload(
                block=block,
                output=output,
                blob_data=payload.blob_data,
                build_context=build_context,
            )
        )

    return artifacts


def _index_outputs_by_block_id(
    bundle: BundleModel,
    bundle_path: Path,
) -> dict[str, BundleBlockOutputRecord]:
    outputs_by_block: dict[str, BundleBlockOutputRecord] = {}
    for output in bundle.block_outputs:
        existing = outputs_by_block.get(output.block_id)
        if existing is not None:
            raise BundleError.from_message(
                f"bundle has duplicate persisted render outputs for block '{output.block_id}'",
                context=ErrorContext(source_path=bundle_path, block_id=output.block_id),
            )
        outputs_by_block[output.block_id] = output
    return outputs_by_block


def _render_output_payload(
    *,
    block: ExecutableBlockNode,
    output: BundleBlockOutputRecord,
    blob_data: bytes,
    build_context: BuildContext,
) -> RenderedArtifact:
    if (
        output.output_kind is BundleOutputKind.CHART_SPEC
        and output.format is BundleOutputFormat.VEGA_JSON
    ):
        spec = _decode_chart_spec(block, blob_data)
        return render_chart_spec_artifact(
            block=block,
            spec=spec,
            build_context=build_context,
        )

    if (
        output.output_kind is BundleOutputKind.TABLE_FRAME
        and output.format is BundleOutputFormat.PARQUET
    ):
        frame = _decode_table_frame(block, blob_data)
        return render_table_frame_artifact(
            block=block,
            frame=frame,
            build_context=build_context,
        )

    raise BundleError.from_message(
        f"unsupported persisted render output '{output.output_kind.value}' with format '{output.format.value}'",
        context=ErrorContext(
            source_path=block.location.source_path
            if block.location is not None
            else None,
            block_id=block.node_id,
            block_type=block.block_type,
            block_index=block.block_index,
            location=block.location,
        ),
    )


def _decode_chart_spec(
    block: ExecutableBlockNode, blob_data: bytes
) -> dict[str, object]:
    try:
        return vega_json_bytes_to_spec(blob_data)
    except Exception as exc:
        raise BundleError.from_exception(
            f"bundle chart output for block '{block.node_id}' is not readable Vega-Lite JSON",
            exc,
            context=ErrorContext(
                source_path=block.location.source_path
                if block.location is not None
                else None,
                block_id=block.node_id,
                block_type=block.block_type,
                block_index=block.block_index,
                location=block.location,
            ),
            source_snippet=block.location.snippet
            if block.location is not None
            else None,
        ) from exc


def _decode_table_frame(block: ExecutableBlockNode, blob_data: bytes):
    try:
        return output_parquet_bytes_to_frame(blob_data)
    except Exception as exc:
        raise BundleError.from_exception(
            f"bundle table output for block '{block.node_id}' is not readable parquet",
            exc,
            context=ErrorContext(
                source_path=block.location.source_path
                if block.location is not None
                else None,
                block_id=block.node_id,
                block_type=block.block_type,
                block_index=block.block_index,
                location=block.location,
            ),
            source_snippet=block.location.snippet
            if block.location is not None
            else None,
        ) from exc


__all__ = ["render_bundle"]
