from __future__ import annotations

import hashlib
from pathlib import Path

from mdcc.bundle.builder import BUNDLE_FORMAT_VERSION
from mdcc.bundle.datasets import parquet_bytes_to_frame
from mdcc.bundle.store import REQUIRED_TABLES, list_tables, read_bundle
from mdcc.errors import BundleValidationError
from mdcc.models import BundleDatasetRole, BundleModel


def validate_bundle(path: Path) -> BundleModel:
    _validate_required_tables(path)
    bundle = read_bundle(path)
    _validate_meta(bundle)
    _validate_dataset_identity(bundle)
    _validate_block_dataset_links(bundle)
    return bundle


def _validate_required_tables(path: Path) -> None:
    tables = list_tables(path)
    missing = sorted(REQUIRED_TABLES - tables)
    if missing:
        raise BundleValidationError.from_message(
            f"invalid bundle: missing required table '{missing[0]}'"
        )


def _validate_meta(bundle: BundleModel) -> None:
    if bundle.meta.format_version != BUNDLE_FORMAT_VERSION:
        raise BundleValidationError.from_message(
            f"invalid bundle: unsupported bundle format version '{bundle.meta.format_version}'"
        )

    source_hash = hashlib.sha256(
        bundle.document.source_text.encode("utf-8")
    ).hexdigest()
    if source_hash != bundle.meta.source_sha256:
        raise BundleValidationError.from_message(
            "invalid bundle: canonical source hash does not match stored source text"
        )


def _validate_dataset_identity(bundle: BundleModel) -> None:
    payloads = {payload.payload_id: payload for payload in bundle.dataset_payloads}
    names: set[str] = set()
    dataset_ids: set[str] = set()
    for dataset in bundle.datasets:
        if dataset.dataset_id in dataset_ids:
            raise BundleValidationError.from_message(
                f"invalid bundle: duplicate dataset id '{dataset.dataset_id}'"
            )
        dataset_ids.add(dataset.dataset_id)

        if dataset.name in names:
            raise BundleValidationError.from_message(
                f"invalid bundle: duplicate dataset name '{dataset.name}'"
            )
        names.add(dataset.name)

        payload = payloads.get(dataset.payload_id)
        if payload is None:
            raise BundleValidationError.from_message(
                f"invalid bundle: persisted dataset '{dataset.name}' references missing payload '{dataset.payload_id}'"
            )
        try:
            parquet_bytes_to_frame(payload.blob_data)
        except Exception as exc:
            raise BundleValidationError.from_exception(
                f"invalid bundle: persisted dataset '{dataset.name}' payload is not readable parquet",
                exc,
            ) from exc


def _validate_block_dataset_links(bundle: BundleModel) -> None:
    block_ids = {block.block_id for block in bundle.blocks}
    dataset_ids = {dataset.dataset_id for dataset in bundle.datasets}
    allowed_roles = {role.value for role in BundleDatasetRole}
    for link in bundle.block_datasets:
        if link.block_id not in block_ids:
            raise BundleValidationError.from_message(
                f"invalid bundle: block-to-dataset mapping references unknown block '{link.block_id}'"
            )
        if link.dataset_id not in dataset_ids:
            raise BundleValidationError.from_message(
                f"invalid bundle: block-to-dataset mapping references unknown dataset '{link.dataset_id}'"
            )
        if link.role.value not in allowed_roles:
            raise BundleValidationError.from_message(
                f"invalid bundle: unsupported dataset role '{link.role.value}'"
            )
