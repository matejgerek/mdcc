from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path
from unittest.mock import patch
import pytest

from mdcc.bundle.commands import BundleCreateOptions, create_bundle
from mdcc.bundle.inspect import (
    format_bundle_annotated,
    format_bundle_overview,
    format_bundle_source,
)
from mdcc.bundle.sql import dataset_head, dataset_schema, list_datasets, run_sql
from mdcc.bundle.store import read_bundle
from mdcc.bundle.validate import validate_bundle
from mdcc.errors import BundleError, ReadError
from mdcc.executor.runner import run_payloads as real_run_payloads


def _write_source(tmp_path: Path, body: str) -> Path:
    source = tmp_path / "report.md"
    source.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return source


def _strip_inspect_overlays(text: str) -> str:
    return "".join(
        line
        for line in text.splitlines(keepends=True)
        if not line.startswith("<!-- mdcc-inspect:")
    )


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


def test_bundle_inspect_source_returns_exact_stored_text(tmp_path: Path) -> None:
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

    assert format_bundle_source(bundle_path) == source.read_text(encoding="utf-8")


def test_bundle_block_source_lines_include_frontmatter_offset(tmp_path: Path) -> None:
    source = _write_source(
        tmp_path,
        """
        ---
        title: Frontmatter Example
        author: mdcc
        ---

        # Title

        ```mdcc_table
        pd.DataFrame({"value": [1]})
        ```
        """,
    )
    bundle_path = create_bundle(
        BundleCreateOptions(
            input_path=source,
            output_path=tmp_path / "frontmatter.mdcx",
        )
    )

    bundle = read_bundle(bundle_path)

    assert bundle.blocks[0].source_start_line == 8
    assert bundle.blocks[0].source_end_line == 10


def test_bundle_inspect_overview_includes_block_dataset_and_relationship_sections(
    tmp_path: Path,
) -> None:
    data_path = tmp_path / "sales.csv"
    data_path.write_text("region,revenue\nna,10\neu,20\n", encoding="utf-8")
    source = _write_source(
        tmp_path,
        """
        # Revenue

        ```mdcc_table label="tbl:revenue" caption="Revenue by region"
        frame = pd.read_csv("sales.csv")
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

    output = format_bundle_overview(bundle_path)

    assert "block details:" in output
    assert "dataset details:" in output
    assert "relationships:" in output
    assert "block-0001 | mdcc_table" in output
    assert "label=tbl:revenue" in output
    assert "caption=Revenue by region" in output
    assert "dset_001 | ds_block_0001_primary | roles=input,primary" in output
    assert "block-0001 -> input:dset_001" in output
    assert "primary:dset_001" in output


def test_bundle_inspect_annotated_inserts_overlay_before_block_fence(
    tmp_path: Path,
) -> None:
    data_path = tmp_path / "sales.csv"
    data_path.write_text("region,revenue\nna,10\neu,20\n", encoding="utf-8")
    source = _write_source(
        tmp_path,
        """
        # Revenue

        ```mdcc_table
        frame = pd.read_csv("sales.csv")
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

    output = format_bundle_annotated(bundle_path)

    assert "<!-- mdcc-inspect:block id=block-0001 type=mdcc_table -->" in output
    assert (
        "<!-- mdcc-inspect:dataset role=input dataset_id=dset_001 "
        "name=ds_block_0001_primary source_kind=read_csv -->"
    ) in output
    assert (
        "<!-- mdcc-inspect:dataset role=primary dataset_id=dset_001 "
        "name=ds_block_0001_primary source_kind=read_csv -->"
    ) in output
    assert output.index(
        "<!-- mdcc-inspect:block id=block-0001 type=mdcc_table -->"
    ) < output.index("```mdcc_table")


def test_bundle_inspect_annotated_preserves_original_source_lines(
    tmp_path: Path,
) -> None:
    data_path = tmp_path / "sales.csv"
    data_path.write_text("region,revenue\nna,10\neu,20\n", encoding="utf-8")
    source = _write_source(
        tmp_path,
        """
        # Revenue

        ```mdcc_table
        frame = pd.read_csv("sales.csv")
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

    annotated = format_bundle_annotated(bundle_path)

    assert _strip_inspect_overlays(annotated) == source.read_text(encoding="utf-8")


def test_bundle_inspect_annotated_places_overlay_at_block_fence_with_frontmatter(
    tmp_path: Path,
) -> None:
    source = _write_source(
        tmp_path,
        """
        ---
        title: Frontmatter Example
        author: mdcc
        ---

        # Title

        ```mdcc_table
        pd.DataFrame({"value": [1]})
        ```
        """,
    )
    bundle_path = create_bundle(
        BundleCreateOptions(
            input_path=source,
            output_path=tmp_path / "frontmatter.mdcx",
        )
    )

    lines = format_bundle_annotated(bundle_path).splitlines()
    overlay_index = lines.index(
        "<!-- mdcc-inspect:block id=block-0001 type=mdcc_table -->"
    )
    fence_index = lines.index("```mdcc_table")

    assert overlay_index + 2 == fence_index


def test_bundle_inspect_handles_bundle_without_blocks_or_datasets(
    tmp_path: Path,
) -> None:
    source = _write_source(
        tmp_path,
        """
        # Notes

        Plain markdown only.
        """,
    )
    bundle_path = create_bundle(
        BundleCreateOptions(
            input_path=source,
            output_path=tmp_path / "notes.mdcx",
        )
    )

    overview = format_bundle_overview(bundle_path)
    annotated = format_bundle_annotated(bundle_path)

    assert "blocks: 0" in overview
    assert "datasets: 0" in overview
    assert overview.count("- (none)") >= 3
    assert annotated == source.read_text(encoding="utf-8")


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


def test_create_bundle_uses_standard_reader_errors_for_invalid_utf8(
    tmp_path: Path,
) -> None:
    source = tmp_path / "broken.md"
    source.write_bytes(b"\xff")

    with pytest.raises(ReadError) as exc_info:
        create_bundle(
            BundleCreateOptions(
                input_path=source,
                output_path=tmp_path / "broken.mdcx",
            )
        )

    assert "failed to read source file" in str(exc_info.value)


def test_read_bundle_wraps_invalid_row_values_as_bundle_error(tmp_path: Path) -> None:
    bundle_path = tmp_path / "broken-rows.mdcx"
    connection = sqlite3.connect(bundle_path)
    try:
        connection.executescript(
            """
            CREATE TABLE bundle_meta (
                format_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                mdcc_version TEXT NOT NULL,
                source_filename TEXT,
                source_sha256 TEXT NOT NULL
            );
            INSERT INTO bundle_meta VALUES ('1', 'now', '0.1.0', NULL, 'abc');

            CREATE TABLE documents (
                document_id TEXT PRIMARY KEY,
                title TEXT,
                source_text TEXT NOT NULL
            );
            INSERT INTO documents VALUES ('doc_main', NULL, '# report');

            CREATE TABLE blocks (
                block_id TEXT PRIMARY KEY,
                block_type TEXT NOT NULL,
                source_start_line INTEGER NOT NULL,
                source_end_line INTEGER NOT NULL,
                label TEXT,
                caption TEXT
            );
            INSERT INTO blocks VALUES ('block-0001', 'not_a_block_type', 1, 1, NULL, NULL);

            CREATE TABLE datasets (
                dataset_id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                format TEXT NOT NULL,
                role_summary TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                column_count INTEGER NOT NULL,
                source_kind TEXT NOT NULL,
                payload_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL
            );

            CREATE TABLE dataset_columns (
                dataset_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                column_name TEXT NOT NULL,
                logical_type TEXT NOT NULL,
                nullable INTEGER NOT NULL
            );

            CREATE TABLE block_datasets (
                block_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                role TEXT NOT NULL
            );

            CREATE TABLE dataset_payloads (
                payload_id TEXT PRIMARY KEY,
                blob_data BLOB NOT NULL
            );
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(BundleError) as exc_info:
        read_bundle(bundle_path)

    assert "stored row contents failed validation" in str(exc_info.value)
