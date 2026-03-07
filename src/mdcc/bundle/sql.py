from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from mdcc.bundle.datasets import parquet_bytes_to_frame
from mdcc.bundle.store import read_bundle
from mdcc.errors import InspectionError, SqlExecutionError
from mdcc.models import BundleDatasetRecord, BundleModel


def list_datasets(bundle_path: Path) -> pd.DataFrame:
    bundle = read_bundle(bundle_path)
    rows = [
        {
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "role_summary": dataset.role_summary,
            "source_kind": dataset.source_kind.value,
            "rows": dataset.row_count,
            "columns": dataset.column_count,
            "format": dataset.format,
        }
        for dataset in bundle.datasets
    ]
    return pd.DataFrame(rows)


def dataset_summary(bundle_path: Path, dataset_id: str) -> pd.DataFrame:
    bundle = read_bundle(bundle_path)
    dataset = require_dataset(bundle, dataset_id)
    return pd.DataFrame(
        [
            {
                "dataset_id": dataset.dataset_id,
                "name": dataset.name,
                "role_summary": dataset.role_summary,
                "source_kind": dataset.source_kind.value,
                "row_count": dataset.row_count,
                "column_count": dataset.column_count,
                "format": dataset.format,
                "fingerprint": dataset.fingerprint,
                "payload_id": dataset.payload_id,
            }
        ]
    )


def dataset_schema(bundle_path: Path, dataset_id: str) -> pd.DataFrame:
    bundle = read_bundle(bundle_path)
    dataset = require_dataset(bundle, dataset_id)
    return pd.DataFrame(
        [
            {
                "ordinal": column.ordinal,
                "column_name": column.column_name,
                "logical_type": column.logical_type,
                "nullable": column.nullable,
            }
            for column in dataset.columns
        ]
    )


def dataset_head(bundle_path: Path, dataset_id: str, rows: int) -> pd.DataFrame:
    dataset, payload = _dataset_with_payload(read_bundle(bundle_path), dataset_id)
    return parquet_bytes_to_frame(payload).head(rows)


def extract_source(bundle_path: Path, output_path: Path) -> Path:
    bundle = read_bundle(bundle_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(bundle.document.source_text, encoding="utf-8")
    return output_path


def extract_dataset(bundle_path: Path, dataset_id: str, output_path: Path) -> Path:
    _, payload = _dataset_with_payload(read_bundle(bundle_path), dataset_id)
    frame = parquet_bytes_to_frame(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    return output_path


def run_sql(bundle_path: Path, query: str) -> pd.DataFrame:
    bundle = read_bundle(bundle_path)
    payloads = {
        payload.payload_id: payload.blob_data for payload in bundle.dataset_payloads
    }
    connection = duckdb.connect(database=":memory:")
    try:
        for dataset in bundle.datasets:
            blob_data = payloads.get(dataset.payload_id)
            if blob_data is None:
                continue
            frame = parquet_bytes_to_frame(blob_data)
            connection.register(dataset.name, frame)
        try:
            return connection.execute(query).fetch_df()
        except duckdb.Error as exc:
            raise SqlExecutionError.from_exception("sql query failed", exc) from exc
    finally:
        connection.close()


def require_dataset(bundle: BundleModel, dataset_id: str) -> BundleDatasetRecord:
    for dataset in bundle.datasets:
        if dataset.dataset_id == dataset_id:
            return dataset
    raise InspectionError.from_message(f"unknown dataset id: {dataset_id}")


def _dataset_with_payload(
    bundle: BundleModel,
    dataset_id: str,
) -> tuple[BundleDatasetRecord, bytes]:
    dataset = require_dataset(bundle, dataset_id)
    payloads = {
        payload.payload_id: payload.blob_data for payload in bundle.dataset_payloads
    }
    blob_data = payloads.get(dataset.payload_id)
    if blob_data is None:
        raise InspectionError.from_message(
            f"unknown dataset payload for dataset id: {dataset_id}"
        )
    return dataset, blob_data
