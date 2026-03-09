from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from mdcc.bundle.store import read_bundle
from mdcc.errors import InspectionError
from mdcc.models import (
    BundleBlockDatasetLink,
    BundleBlockRecord,
    BundleDatasetRecord,
    BundleModel,
)


def format_bundle_overview(bundle_path: Path) -> str:
    bundle = read_bundle(bundle_path)
    datasets_by_id = _datasets_by_id(bundle)
    links_by_block = _links_by_block(bundle, datasets_by_id)
    lines = [
        f"bundle: {bundle_path}",
        f"format_version: {bundle.meta.format_version}",
        f"created_at: {bundle.meta.created_at}",
        f"mdcc_version: {bundle.meta.mdcc_version}",
        f"source_filename: {bundle.meta.source_filename or '-'}",
        f"title: {bundle.document.title or '-'}",
        f"blocks: {len(bundle.blocks)}",
        f"datasets: {len(bundle.datasets)}",
        f"payloads: {len(bundle.dataset_payloads)}",
        "",
        "block details:",
    ]
    lines.extend(_format_block_details(bundle.blocks))
    lines.extend(["", "dataset details:"])
    lines.extend(_format_dataset_details(bundle.datasets))
    lines.extend(["", "relationships:"])
    lines.extend(_format_relationships(bundle.blocks, links_by_block))
    return "\n".join(lines)


def format_bundle_source(bundle_path: Path) -> str:
    bundle = read_bundle(bundle_path)
    return bundle.document.source_text


def format_bundle_annotated(bundle_path: Path) -> str:
    bundle = read_bundle(bundle_path)
    datasets_by_id = _datasets_by_id(bundle)
    overlays_by_start_line = _overlay_lines_by_start_line(bundle, datasets_by_id)
    source_lines = bundle.document.source_text.splitlines(keepends=True)
    newline = _detect_newline(bundle.document.source_text)
    if not overlays_by_start_line:
        return bundle.document.source_text

    rendered: list[str] = []
    for line_number, line in enumerate(source_lines, start=1):
        overlay_lines = overlays_by_start_line.get(line_number)
        if overlay_lines is not None:
            rendered.extend(f"{overlay}{newline}" for overlay in overlay_lines)
        rendered.append(line)
    return "".join(rendered)


def _format_block_details(blocks: list[BundleBlockRecord]) -> list[str]:
    if not blocks:
        return ["- (none)"]
    return [
        (
            f"- {block.block_id} | {block.block_type.value} | "
            f"lines {block.source_start_line}-{block.source_end_line} | "
            f"label={block.label or '-'} | caption={block.caption or '-'}"
        )
        for block in blocks
    ]


def _format_dataset_details(datasets: list[BundleDatasetRecord]) -> list[str]:
    if not datasets:
        return ["- (none)"]
    return [
        (
            f"- {dataset.dataset_id} | {dataset.name} | roles={dataset.role_summary} | "
            f"source={dataset.source_kind.value} | rows={dataset.row_count} | "
            f"columns={dataset.column_count} | payload={dataset.payload_id}"
        )
        for dataset in datasets
    ]


def _format_relationships(
    blocks: list[BundleBlockRecord],
    links_by_block: dict[str, list[tuple[BundleBlockDatasetLink, BundleDatasetRecord]]],
) -> list[str]:
    if not blocks:
        return ["- (none)"]

    lines: list[str] = []
    for block in blocks:
        linked = links_by_block.get(block.block_id, [])
        if not linked:
            lines.append(f"- {block.block_id} -> (none)")
            continue
        relationship_summary = ", ".join(
            (
                f"{link.role.value}:{dataset.dataset_id} "
                f"({dataset.name}; source={dataset.source_kind.value})"
            )
            for link, dataset in linked
        )
        lines.append(f"- {block.block_id} -> {relationship_summary}")
    return lines


def _datasets_by_id(bundle: BundleModel) -> dict[str, BundleDatasetRecord]:
    return {dataset.dataset_id: dataset for dataset in bundle.datasets}


def _links_by_block(
    bundle: BundleModel,
    datasets_by_id: dict[str, BundleDatasetRecord],
) -> dict[str, list[tuple[BundleBlockDatasetLink, BundleDatasetRecord]]]:
    links_by_block: dict[
        str, list[tuple[BundleBlockDatasetLink, BundleDatasetRecord]]
    ] = defaultdict(list)
    known_block_ids = {block.block_id for block in bundle.blocks}
    for link in bundle.block_datasets:
        if link.block_id not in known_block_ids:
            raise InspectionError.from_message(
                f"unknown block id referenced in bundle relationships: {link.block_id}"
            )
        dataset = datasets_by_id.get(link.dataset_id)
        if dataset is None:
            raise InspectionError.from_message(
                f"unknown dataset id referenced in bundle relationships: {link.dataset_id}"
            )
        links_by_block[link.block_id].append((link, dataset))
    return dict(links_by_block)


def _overlay_lines_by_start_line(
    bundle: BundleModel,
    datasets_by_id: dict[str, BundleDatasetRecord],
) -> dict[int, list[str]]:
    source_lines = bundle.document.source_text.splitlines(keepends=True)
    links_by_block = _links_by_block(bundle, datasets_by_id)
    overlays: dict[int, list[str]] = {}
    for block in bundle.blocks:
        block_links = links_by_block.get(block.block_id, [])
        if not block_links:
            continue
        _validate_block_span(block, source_lines)
        overlay_lines = [
            f"<!-- mdcc-inspect:block id={block.block_id} type={block.block_type.value} -->"
        ]
        overlay_lines.extend(
            (
                "<!-- mdcc-inspect:dataset "
                f"role={link.role.value} "
                f"dataset_id={dataset.dataset_id} "
                f"name={dataset.name} "
                f"source_kind={dataset.source_kind.value} -->"
            )
            for link, dataset in block_links
        )
        overlays[block.source_start_line] = overlay_lines
    return overlays


def _validate_block_span(block: BundleBlockRecord, source_lines: list[str]) -> None:
    line_count = len(source_lines)
    if block.source_start_line > block.source_end_line:
        raise InspectionError.from_message(
            f"invalid block span for block id: {block.block_id}"
        )
    if line_count == 0:
        raise InspectionError.from_message(
            f"cannot project annotated source for empty document bundle: {block.block_id}"
        )
    if block.source_start_line > line_count or block.source_end_line > line_count:
        raise InspectionError.from_message(
            f"stored block span falls outside canonical source for block id: {block.block_id}"
        )


def _detect_newline(source_text: str) -> str:
    if "\r\n" in source_text:
        return "\r\n"
    if "\n" in source_text:
        return "\n"
    if "\r" in source_text:
        return "\r"
    return "\n"


__all__ = [
    "format_bundle_annotated",
    "format_bundle_overview",
    "format_bundle_source",
]
