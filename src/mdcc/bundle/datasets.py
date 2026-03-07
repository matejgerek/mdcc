from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import hashlib
import re
from typing import Any

import pandas as pd
from pandas.api import types as pd_types

from mdcc.models import (
    BundleBlockDatasetLink,
    BundleDatasetColumn,
    BundleDatasetRecord,
    BundleDatasetRole,
    BundlePayloadRecord,
    CompiledBlockRecord,
    DatasetSourceKind,
    RuntimeDatasetCapture,
)

_ROLE_ORDER = {
    BundleDatasetRole.INPUT: 0,
    BundleDatasetRole.PRIMARY: 1,
    BundleDatasetRole.SUPPORTING: 2,
}

_SOURCE_KIND_PRIORITY = {
    DatasetSourceKind.READ_CSV: 0,
    DatasetSourceKind.READ_JSON: 0,
    DatasetSourceKind.READ_EXCEL: 0,
    DatasetSourceKind.READ_PARQUET: 0,
    DatasetSourceKind.MANUAL_PERSIST: 1,
    DatasetSourceKind.RENDER_PRIMARY: 2,
}


@dataclass(slots=True)
class _DatasetCandidate:
    frame: pd.DataFrame
    payload_bytes: bytes
    fingerprint: str
    source_kind: DatasetSourceKind
    name: str
    roles: set[BundleDatasetRole] = field(default_factory=set)


def build_bundle_datasets(
    compiled_blocks: list[CompiledBlockRecord],
) -> tuple[
    list[BundleDatasetRecord], list[BundleBlockDatasetLink], list[BundlePayloadRecord]
]:
    """Normalize persisted bundle datasets across compiled blocks."""
    dataset_records: list[BundleDatasetRecord] = []
    block_links: list[BundleBlockDatasetLink] = []
    payload_records: list[BundlePayloadRecord] = []
    payload_ids_by_fingerprint: dict[str, str] = {}
    next_payload_index = 1
    next_dataset_index = 1

    for record in compiled_blocks:
        candidates = _collect_block_candidates(record)
        merged = _merge_block_candidates(record, candidates)
        for candidate in merged:
            payload_id = payload_ids_by_fingerprint.get(candidate.fingerprint)
            if payload_id is None:
                payload_id = f"payload_{next_payload_index:03d}"
                next_payload_index += 1
                payload_ids_by_fingerprint[candidate.fingerprint] = payload_id
                payload_records.append(
                    BundlePayloadRecord(
                        payload_id=payload_id, blob_data=candidate.payload_bytes
                    )
                )

            dataset_id = f"dset_{next_dataset_index:03d}"
            next_dataset_index += 1
            columns = _dataset_columns(candidate.frame)
            dataset_records.append(
                BundleDatasetRecord(
                    dataset_id=dataset_id,
                    name=candidate.name,
                    format="parquet",
                    role_summary=",".join(
                        role.value for role in _sorted_roles(candidate.roles)
                    ),
                    row_count=len(candidate.frame.index),
                    column_count=len(candidate.frame.columns),
                    source_kind=candidate.source_kind,
                    payload_id=payload_id,
                    fingerprint=candidate.fingerprint,
                    columns=columns,
                )
            )
            for role in _sorted_roles(candidate.roles):
                block_links.append(
                    BundleBlockDatasetLink(
                        block_id=record.payload.block.node_id,
                        dataset_id=dataset_id,
                        role=role,
                    )
                )

    return dataset_records, block_links, payload_records


def load_capture_frame(capture: RuntimeDatasetCapture) -> pd.DataFrame:
    return pd.read_parquet(capture.payload_path)


def dataframe_to_parquet_bytes(frame: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.to_parquet(buffer, index=False)
    return buffer.getvalue()


def parquet_bytes_to_frame(blob_data: bytes) -> pd.DataFrame:
    return pd.read_parquet(BytesIO(blob_data))


def _collect_block_candidates(record: CompiledBlockRecord) -> list[_DatasetCandidate]:
    block_id = _sql_name_block_id(record.payload.block.node_id)
    candidates: list[_DatasetCandidate] = []

    for capture in record.dataset_captures:
        frame = load_capture_frame(capture)
        candidates.append(
            _candidate(
                frame=frame,
                source_kind=capture.source_kind,
                name=f"ds_{block_id}_input_{capture.ordinal + 1}",
                role=BundleDatasetRole.INPUT,
            )
        )

    typed = record.typed_result
    if hasattr(typed, "value") and isinstance(typed.value, pd.DataFrame):
        candidates.append(
            _candidate(
                frame=typed.value,
                source_kind=DatasetSourceKind.RENDER_PRIMARY,
                name=f"ds_{block_id}_primary",
                role=BundleDatasetRole.PRIMARY,
            )
        )
    else:
        candidates.extend(_chart_candidates(record))

    return candidates


def _chart_candidates(record: CompiledBlockRecord) -> list[_DatasetCandidate]:
    spec = getattr(record.typed_result, "spec", {})
    if not isinstance(spec, dict):
        return []

    candidates: list[_DatasetCandidate] = []
    block_id = _sql_name_block_id(record.payload.block.node_id)
    source = spec.get("data")
    source_name = source.get("name") if isinstance(source, dict) else None
    datasets = spec.get("datasets")

    if isinstance(source, dict) and "values" in source:
        frame = _values_to_frame(source["values"])
        if frame is not None:
            candidates.append(
                _candidate(
                    frame=frame,
                    source_kind=DatasetSourceKind.RENDER_PRIMARY,
                    name=f"ds_{block_id}_primary",
                    role=BundleDatasetRole.PRIMARY,
                )
            )

    if isinstance(datasets, dict):
        supporting_index = 1
        for dataset_name, values in datasets.items():
            frame = _values_to_frame(values)
            if frame is None:
                continue
            if dataset_name == source_name:
                role = BundleDatasetRole.PRIMARY
                name = f"ds_{block_id}_primary"
            else:
                role = BundleDatasetRole.SUPPORTING
                name = f"ds_{block_id}_supporting_{supporting_index}"
                supporting_index += 1
            candidates.append(
                _candidate(
                    frame=frame,
                    source_kind=DatasetSourceKind.RENDER_PRIMARY,
                    name=name,
                    role=role,
                )
            )

    return candidates


def _candidate(
    *,
    frame: pd.DataFrame,
    source_kind: DatasetSourceKind,
    name: str,
    role: BundleDatasetRole,
) -> _DatasetCandidate:
    payload_bytes = dataframe_to_parquet_bytes(frame)
    fingerprint = hashlib.sha256(payload_bytes).hexdigest()
    return _DatasetCandidate(
        frame=frame,
        payload_bytes=payload_bytes,
        fingerprint=fingerprint,
        source_kind=source_kind,
        name=name,
        roles={role},
    )


def _merge_block_candidates(
    record: CompiledBlockRecord,
    candidates: list[_DatasetCandidate],
) -> list[_DatasetCandidate]:
    merged: dict[str, _DatasetCandidate] = {}
    block_id = _sql_name_block_id(record.payload.block.node_id)

    input_index = 1
    supporting_index = 1
    for candidate in candidates:
        existing = merged.get(candidate.fingerprint)
        if existing is None:
            if BundleDatasetRole.INPUT in candidate.roles:
                candidate.name = f"ds_{block_id}_input_{input_index}"
                input_index += 1
            elif BundleDatasetRole.SUPPORTING in candidate.roles:
                candidate.name = f"ds_{block_id}_supporting_{supporting_index}"
                supporting_index += 1
            merged[candidate.fingerprint] = candidate
            continue

        existing.roles.update(candidate.roles)
        if (
            _SOURCE_KIND_PRIORITY[candidate.source_kind]
            < _SOURCE_KIND_PRIORITY[existing.source_kind]
        ):
            existing.source_kind = candidate.source_kind
        if BundleDatasetRole.PRIMARY in candidate.roles:
            existing.name = f"ds_{block_id}_primary"
        elif (
            BundleDatasetRole.INPUT in candidate.roles
            and BundleDatasetRole.PRIMARY not in existing.roles
        ):
            existing.name = candidate.name

    return list(merged.values())


def _dataset_columns(frame: pd.DataFrame) -> list[BundleDatasetColumn]:
    columns: list[BundleDatasetColumn] = []
    for ordinal, column_name in enumerate(frame.columns):
        series = frame.iloc[:, ordinal]
        columns.append(
            BundleDatasetColumn(
                ordinal=ordinal,
                column_name=str(column_name),
                logical_type=_logical_type(series),
                nullable=bool(series.isna().any()),
            )
        )
    return columns


def _logical_type(series: pd.Series[Any]) -> str:
    dtype = series.dtype
    if pd_types.is_bool_dtype(dtype):
        return "boolean"
    if pd_types.is_integer_dtype(dtype):
        return "integer"
    if pd_types.is_float_dtype(dtype):
        return "float"
    if pd_types.is_datetime64_any_dtype(dtype):
        return "datetime"
    if pd_types.is_timedelta64_dtype(dtype):
        return "timedelta"
    if pd_types.is_string_dtype(dtype):
        return "string"
    if pd_types.is_object_dtype(dtype):
        return "object"
    return str(dtype)


def _values_to_frame(values: Any) -> pd.DataFrame | None:
    try:
        return pd.DataFrame(values)
    except Exception:
        return None


def _sorted_roles(roles: set[BundleDatasetRole]) -> list[BundleDatasetRole]:
    return sorted(roles, key=_ROLE_ORDER.__getitem__)


def _sql_name_block_id(block_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", block_id)
