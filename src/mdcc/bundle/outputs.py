from __future__ import annotations

import json

from mdcc.bundle.datasets import dataframe_to_parquet_bytes, parquet_bytes_to_frame
from mdcc.models import (
    BundleBlockOutputRecord,
    BundleOutputFormat,
    BundleOutputKind,
    BundleOutputPayloadRecord,
    ChartResult,
    CompiledBlockRecord,
    TableResult,
)


def build_bundle_outputs(
    compiled_blocks: list[CompiledBlockRecord],
) -> tuple[list[BundleBlockOutputRecord], list[BundleOutputPayloadRecord]]:
    block_outputs: list[BundleBlockOutputRecord] = []
    payloads: list[BundleOutputPayloadRecord] = []

    for index, record in enumerate(compiled_blocks, start=1):
        payload_id = f"output_payload_{index:03d}"
        typed_result = record.typed_result

        if isinstance(typed_result, ChartResult):
            blob_data = json.dumps(
                typed_result.spec,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            output_kind = BundleOutputKind.CHART_SPEC
            format_name = BundleOutputFormat.VEGA_JSON
        elif isinstance(typed_result, TableResult):
            blob_data = dataframe_to_parquet_bytes(typed_result.value)
            output_kind = BundleOutputKind.TABLE_FRAME
            format_name = BundleOutputFormat.PARQUET
        else:
            msg = f"unsupported typed result for bundle output: {type(typed_result).__name__}"
            raise TypeError(msg)

        payloads.append(
            BundleOutputPayloadRecord(
                payload_id=payload_id,
                blob_data=blob_data,
            )
        )
        block_outputs.append(
            BundleBlockOutputRecord(
                block_id=record.payload.block.node_id,
                output_kind=output_kind,
                format=format_name,
                payload_id=payload_id,
            )
        )

    return block_outputs, payloads


def vega_json_bytes_to_spec(blob_data: bytes) -> dict[str, object]:
    payload = json.loads(blob_data.decode("utf-8"))
    if not isinstance(payload, dict):
        msg = "serialized Vega-Lite output must decode to a JSON object"
        raise ValueError(msg)
    return payload


def output_parquet_bytes_to_frame(blob_data: bytes):
    return parquet_bytes_to_frame(blob_data)


__all__ = [
    "build_bundle_outputs",
    "output_parquet_bytes_to_frame",
    "vega_json_bytes_to_spec",
]
