from __future__ import annotations

from datetime import datetime, UTC
import hashlib

from mdcc import __version__
from mdcc.bundle.datasets import build_bundle_datasets
from mdcc.bundle.outputs import build_bundle_outputs
from mdcc.models import (
    BundleBlockRecord,
    BundleDocumentRecord,
    BundleMetaRecord,
    BundleModel,
    CompiledBlockRecord,
    DocumentModel,
)

BUNDLE_FORMAT_VERSION = "1"


def build_bundle_model(
    *,
    document: DocumentModel,
    source_text: str,
    compiled_blocks: list[CompiledBlockRecord],
    source_line_offset: int = 0,
) -> BundleModel:
    datasets, block_links, payloads = build_bundle_datasets(compiled_blocks)
    block_outputs, output_payloads = build_bundle_outputs(compiled_blocks)
    return BundleModel(
        meta=BundleMetaRecord(
            format_version=BUNDLE_FORMAT_VERSION,
            created_at=datetime.now(UTC).isoformat(),
            mdcc_version=__version__,
            source_filename=document.source_path.name,
            source_sha256=hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        ),
        document=BundleDocumentRecord(
            document_id="doc_main",
            title=document.frontmatter.title
            if document.frontmatter is not None
            else None,
            source_text=source_text,
        ),
        blocks=[
            _block_record(record, source_line_offset=source_line_offset)
            for record in compiled_blocks
        ],
        datasets=datasets,
        block_datasets=block_links,
        dataset_payloads=payloads,
        block_outputs=block_outputs,
        output_payloads=output_payloads,
    )


def _block_record(
    record: CompiledBlockRecord, *, source_line_offset: int
) -> BundleBlockRecord:
    location = record.payload.block.location
    span = location.span if location is not None else None
    start_line = span.start.line if span is not None else 1
    end_line = span.end.line if span is not None else start_line
    metadata = record.payload.block.metadata
    return BundleBlockRecord(
        block_id=record.payload.block.node_id,
        block_type=record.payload.block.block_type,
        source_start_line=start_line + source_line_offset,
        source_end_line=end_line + source_line_offset,
        label=metadata.label,
        caption=metadata.caption,
    )
