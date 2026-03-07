from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path
from unittest.mock import patch
import pytest

from mdcc.bundle.commands import BundleCreateOptions, create_bundle
from mdcc.bundle.sql import dataset_head, dataset_schema, list_datasets, run_sql
from mdcc.bundle.store import read_bundle
from mdcc.bundle.validate import validate_bundle
from mdcc.executor.runner import run_payloads as real_run_payloads


def _write_source(tmp_path: Path, body: str) -> Path:
    source = tmp_path / "report.md"
    source.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return source


def test_create_bundle_persists_table_input_and_primary_dataset(tmp_path: Path) -> None:
    data_path = tmp_path / "data.csv"
    data_path.write_text("value,region\n1,na\n2,eu\n", encoding="utf-8")
    source = _write_source(
        tmp_path,
        """
        # Revenue

        ```mdcc_table label="tbl:revenue"
        frame = pd.read_csv("data.csv")
        frame
        ```
        """,
    )

    bundle_path = create_bundle(
        BundleCreateOptions(
            input_path=source,
            output_path=tmp_path / "report.mdcx",
        )
    )

    bundle = validate_bundle(bundle_path)
    assert bundle.document.source_text == source.read_text(encoding="utf-8")
    assert len(bundle.datasets) == 1
    assert bundle.datasets[0].role_summary == "input,primary"
    assert bundle.datasets[0].source_kind.value == "read_csv"
    assert bundle.block_datasets[0].role.value == "input"
    assert bundle.block_datasets[1].role.value == "primary"

    head = dataset_head(bundle_path, bundle.datasets[0].dataset_id, 5)
    assert list(head["value"]) == [1, 2]


def test_create_bundle_persists_chart_primary_dataset(tmp_path: Path) -> None:
    source = _write_source(
        tmp_path,
        """
        ```mdcc_chart
        frame = pd.DataFrame({"quarter": ["Q1", "Q2"], "revenue": [10, 20]})
        alt.Chart(frame).mark_bar().encode(x="quarter", y="revenue")
        ```
        """,
    )

    bundle_path = create_bundle(
        BundleCreateOptions(
            input_path=source,
            output_path=tmp_path / "chart.mdcx",
        )
    )

    bundle = read_bundle(bundle_path)
    assert len(bundle.datasets) == 1
    assert bundle.datasets[0].role_summary == "primary"
    frame = dataset_head(bundle_path, bundle.datasets[0].dataset_id, 5)
    assert list(frame["quarter"]) == ["Q1", "Q2"]


def test_bundle_sql_and_schema_commands_use_persisted_datasets(tmp_path: Path) -> None:
    data_path = tmp_path / "sales.csv"
    data_path.write_text("region,revenue\nna,10\nna,12\neu,8\n", encoding="utf-8")
    source = _write_source(
        tmp_path,
        """
        ```mdcc_table
        frame = pd.read_csv("sales.csv")
        frame
        ```
        """,
    )
    bundle_path = create_bundle(
        BundleCreateOptions(
            input_path=source,
            output_path=tmp_path / "sales.mdcx",
        )
    )

    datasets = list_datasets(bundle_path)
    dataset_id = str(datasets.iloc[0]["dataset_id"])
    schema = dataset_schema(bundle_path, dataset_id)
    assert list(schema["column_name"]) == ["region", "revenue"]

    result = run_sql(
        bundle_path,
        "select region, sum(revenue) as revenue from ds_block_0001_primary group by region order by region",
    )
    assert result.to_dict(orient="records") == [
        {"region": "eu", "revenue": 8.0},
        {"region": "na", "revenue": 22.0},
    ]


def test_bundle_extract_source_round_trips_exact_text(tmp_path: Path) -> None:
    source = _write_source(
        tmp_path,
        """
        # Title

        ```mdcc_table
        pd.DataFrame({"value": [1]})
        ```
        """,
    )
    bundle_path = create_bundle(
        BundleCreateOptions(
            input_path=source,
            output_path=tmp_path / "report.mdcx",
        )
    )

    bundle = read_bundle(bundle_path)
    assert bundle.document.source_text == source.read_text(encoding="utf-8")


def test_bundle_create_bypasses_cache_and_reexecutes_blocks(tmp_path: Path) -> None:
    data_path = tmp_path / "data.csv"
    data_path.write_text("value\n1\n2\n", encoding="utf-8")
    source = _write_source(
        tmp_path,
        """
        ```mdcc_table
        frame = pd.read_csv("data.csv")
        frame
        ```
        """,
    )

    create_bundle(
        BundleCreateOptions(
            input_path=source,
            output_path=tmp_path / "first.mdcx",
        )
    )

    calls: list[int] = []

    def _capture(payloads, timeout_seconds):
        calls.append(len(payloads))
        return real_run_payloads(payloads, timeout_seconds)

    with patch("mdcc.compile.run_payloads", side_effect=_capture):
        create_bundle(
            BundleCreateOptions(
                input_path=source,
                output_path=tmp_path / "second.mdcx",
            )
        )

    assert calls == [1]


def test_validate_bundle_rejects_missing_required_table(tmp_path: Path) -> None:
    bundle_path = tmp_path / "broken.mdcx"
    connection = sqlite3.connect(bundle_path)
    try:
        connection.execute("CREATE TABLE bundle_meta (format_version TEXT)")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(Exception) as exc_info:
        validate_bundle(bundle_path)

    assert "missing required table" in str(exc_info.value)


def test_validate_bundle_rejects_corrupt_payload(tmp_path: Path) -> None:
    source = _write_source(
        tmp_path,
        """
        ```mdcc_table
        pd.DataFrame({"value": [1]})
        ```
        """,
    )
    bundle_path = create_bundle(
        BundleCreateOptions(
            input_path=source,
            output_path=tmp_path / "report.mdcx",
        )
    )

    connection = sqlite3.connect(bundle_path)
    try:
        connection.execute(
            "UPDATE dataset_payloads SET blob_data = ?", (b"not-parquet",)
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(Exception) as exc_info:
        validate_bundle(bundle_path)

    assert "payload is not readable parquet" in str(exc_info.value)
