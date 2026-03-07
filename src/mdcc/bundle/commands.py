from __future__ import annotations

from pathlib import Path

import pandas as pd
from pydantic import BaseModel, Field

from mdcc.bundle.builder import build_bundle_model
from mdcc.bundle.sql import (
    dataset_head,
    dataset_schema,
    extract_dataset,
    extract_source,
    list_datasets,
    require_dataset,
    run_sql,
)
from mdcc.bundle.store import read_bundle, write_bundle
from mdcc.bundle.validate import validate_bundle
from mdcc.compile import load_document_model, materialize_compiled_blocks
from mdcc.models import BundleDatasetRecord
from mdcc.utils.workspace import BuildContext


class BundleCreateOptions(BaseModel):
    input_path: Path
    output_path: Path
    timeout_seconds: float = Field(default=30.0, gt=0)
    keep_build_dir: bool = False
    verbose: bool = False


def create_bundle(options: BundleCreateOptions) -> Path:
    source_text = options.input_path.read_text(encoding="utf-8")
    document = load_document_model(options.input_path)
    with BuildContext.create(
        document.source_path, keep=options.keep_build_dir
    ) as build_context:
        compiled_blocks = materialize_compiled_blocks(
            document=document,
            build_context=build_context,
            timeout_seconds=options.timeout_seconds,
            use_cache=False,
            capture_datasets=True,
            verbose=options.verbose,
        )
        bundle = build_bundle_model(
            document=document,
            source_text=source_text,
            compiled_blocks=compiled_blocks,
        )
        return write_bundle(options.output_path, bundle)


def bundle_info(bundle_path: Path) -> str:
    bundle = read_bundle(bundle_path)
    return "\n".join(
        [
            f"bundle: {bundle_path}",
            f"format_version: {bundle.meta.format_version}",
            f"created_at: {bundle.meta.created_at}",
            f"mdcc_version: {bundle.meta.mdcc_version}",
            f"source_filename: {bundle.meta.source_filename or '-'}",
            f"blocks: {len(bundle.blocks)}",
            f"datasets: {len(bundle.datasets)}",
            f"payloads: {len(bundle.dataset_payloads)}",
        ]
    )


def bundle_validate(bundle_path: Path) -> str:
    validate_bundle(bundle_path)
    return f"bundle valid: {bundle_path}"


def dataset_show(bundle_path: Path, dataset_id: str) -> str:
    bundle = read_bundle(bundle_path)
    dataset = require_dataset(bundle, dataset_id)
    return format_dataset_record(dataset)


def dataset_list_table(bundle_path: Path) -> str:
    return format_dataframe(list_datasets(bundle_path))


def dataset_schema_table(bundle_path: Path, dataset_id: str) -> str:
    return format_dataframe(dataset_schema(bundle_path, dataset_id))


def dataset_head_table(bundle_path: Path, dataset_id: str, rows: int) -> str:
    return format_dataframe(dataset_head(bundle_path, dataset_id, rows))


def sql_query_table(bundle_path: Path, query: str) -> str:
    return format_dataframe(run_sql(bundle_path, query))


def extract_source_to_path(bundle_path: Path, output_path: Path) -> Path:
    return extract_source(bundle_path, output_path)


def extract_dataset_to_path(
    bundle_path: Path, dataset_id: str, output_path: Path
) -> Path:
    return extract_dataset(bundle_path, dataset_id, output_path)


def format_dataframe(frame: pd.DataFrame) -> str:
    if frame.empty:
        if len(frame.columns) == 0:
            return "(no rows)"
        return frame.head(0).to_string(index=False)
    return frame.to_string(index=False)


def format_dataset_record(dataset: BundleDatasetRecord) -> str:
    lines = [
        f"dataset_id: {dataset.dataset_id}",
        f"name: {dataset.name}",
        f"role_summary: {dataset.role_summary}",
        f"source_kind: {dataset.source_kind.value}",
        f"row_count: {dataset.row_count}",
        f"column_count: {dataset.column_count}",
        f"format: {dataset.format}",
        f"fingerprint: {dataset.fingerprint}",
        f"payload_id: {dataset.payload_id}",
        "columns:",
    ]
    if not dataset.columns:
        lines.append("  (none)")
    else:
        lines.extend(
            f"  - {column.ordinal}: {column.column_name} ({column.logical_type}, nullable={str(column.nullable).lower()})"
            for column in dataset.columns
        )
    return "\n".join(lines)
