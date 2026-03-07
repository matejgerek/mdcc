from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import pytest

from mdcc import pdf as pdf_module
from mdcc.compile import CompileOptions, compile as run_compile
from mdcc.errors import ExecutionError, ParseError, ValidationError
from mdcc.utils.workspace import BUILD_DIR_NAME


def _require_weasyprint() -> None:
    try:
        pdf_module._load_weasyprint_html()
    except Exception as exc:
        pytest.skip(f"WeasyPrint runtime unavailable: {exc}")


def _write_source(tmp_path: Path, body: str) -> Path:
    source = tmp_path / "report.md"
    source.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return source


def test_compile_generates_pdf_for_document_with_narrative_chart_and_table(
    tmp_path: Path,
) -> None:
    _require_weasyprint()
    source = _write_source(
        tmp_path,
        """
        ---
        title: Revenue Report
        author: Analyst
        date: 2026-03-06
        ---

        # Revenue Report

        This report combines narrative, a chart, and a table.

        ```mdcc_chart
        frame = pd.DataFrame({"quarter": ["Q1", "Q2"], "revenue": [10, 15]})
        alt.Chart(frame).mark_bar().encode(x="quarter", y="revenue")
        ```

        The chart above is followed by a table.

        ```mdcc_table
        pd.DataFrame({"region": ["na", "eu"], "revenue": [10, 15]})
        ```
        """,
    )
    output_path = tmp_path / "output" / "report.pdf"

    result = run_compile(
        CompileOptions(
            input_path=source,
            output_path=output_path,
        )
    )

    assert result == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert output_path.read_bytes().startswith(b"%PDF")
    assert not (tmp_path / BUILD_DIR_NAME).exists()


def test_compile_generates_pdf_for_document_with_block_metadata(
    tmp_path: Path,
) -> None:
    _require_weasyprint()
    source = _write_source(
        tmp_path,
        """
        ---
        title: Metadata Report
        ---

        ```mdcc_chart caption="Revenue by region" label="fig:revenue-region"
        frame = pd.DataFrame({"quarter": ["Q1", "Q2"], "revenue": [10, 15]})
        alt.Chart(frame).mark_bar().encode(x="quarter", y="revenue")
        ```

        ```mdcc_table caption="Regional summary" label="tbl:regional-summary"
        pd.DataFrame({"region": ["na", "eu"], "revenue": [10, 15]})
        ```
        """,
    )
    output_path = tmp_path / "metadata-report.pdf"

    result = run_compile(
        CompileOptions(
            input_path=source,
            output_path=output_path,
        )
    )

    assert result == output_path
    assert output_path.exists()
    assert output_path.read_bytes().startswith(b"%PDF")
    assert not (tmp_path / BUILD_DIR_NAME).exists()


def test_compile_keeps_deterministic_build_artifacts_when_requested(
    tmp_path: Path,
) -> None:
    _require_weasyprint()
    source = _write_source(
        tmp_path,
        """
        ---
        title: Artifact Report
        ---

        Intro text.

        ```mdcc_chart
        frame = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
        alt.Chart(frame).mark_line().encode(x="x", y="y")
        ```

        ```mdcc_table
        pd.DataFrame({"name": ["a", "b"], "value": [1, 2]})
        ```
        """,
    )
    output_path = tmp_path / "artifact-report.pdf"
    build_dir = tmp_path / BUILD_DIR_NAME

    try:
        result = run_compile(
            CompileOptions(
                input_path=source,
                output_path=output_path,
                keep_build_dir=True,
            )
        )

        assert result == output_path
        assert output_path.exists()
        assert build_dir.exists()

        payload_0 = build_dir / "payloads" / "payload_000.py"
        payload_1 = build_dir / "payloads" / "payload_001.py"
        log_0 = build_dir / "logs" / "log_000.txt"
        log_1 = build_dir / "logs" / "log_001.txt"
        chart_svg = build_dir / "charts" / "chart_000.svg"
        table_html = build_dir / "tables" / "table_001.html"
        result_0 = build_dir / "results" / "result_000.json"
        result_1 = build_dir / "results" / "result_001.json"

        for path in (
            payload_0,
            payload_1,
            log_0,
            log_1,
            chart_svg,
            table_html,
            result_0,
            result_1,
        ):
            assert path.exists()

        assert "import pandas as pd" in payload_0.read_text(encoding="utf-8")
        assert "block_id: block-0001" in log_0.read_text(encoding="utf-8")
        assert chart_svg.read_text(encoding="utf-8").startswith("<svg")
        assert "<table" in table_html.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)


def test_compile_propagates_typed_result_validation_failure(tmp_path: Path) -> None:
    source = _write_source(
        tmp_path,
        """
        # Broken table

        ```mdcc_table
        42
        ```
        """,
    )
    output_path = tmp_path / "broken.pdf"

    with pytest.raises(ValidationError) as exc_info:
        run_compile(
            CompileOptions(
                input_path=source,
                output_path=output_path,
            )
        )

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.message == "table block must return a pandas DataFrame"
    assert diagnostic.block_id == "block-0001"
    assert diagnostic.block_index == 0
    assert diagnostic.source_path == source
    assert diagnostic.expected_output_type == "pandas.DataFrame"
    assert diagnostic.actual_output_type == "builtins.int"
    assert not output_path.exists()
    assert not (tmp_path / BUILD_DIR_NAME).exists()


def test_compile_rejects_phase_two_metadata_keys_during_validation(
    tmp_path: Path,
) -> None:
    source = _write_source(
        tmp_path,
        """
        ```mdcc_chart caption="Revenue" width="wide"
        frame = pd.DataFrame({"quarter": ["Q1"], "revenue": [10]})
        alt.Chart(frame).mark_bar().encode(x="quarter", y="revenue")
        ```
        """,
    )
    output_path = tmp_path / "invalid-metadata.pdf"

    with pytest.raises(ValidationError) as exc_info:
        run_compile(
            CompileOptions(
                input_path=source,
                output_path=output_path,
            )
        )

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.stage.value == "validation"
    assert diagnostic.message == (
        "unsupported metadata key 'width' for mdcc_chart in this compiler version"
    )
    assert not output_path.exists()
    assert not (tmp_path / BUILD_DIR_NAME).exists()


def test_compile_rejects_unresolved_cross_reference_during_validation(
    tmp_path: Path,
) -> None:
    source = _write_source(
        tmp_path,
        """
        See @fig:not-found for details.

        ```mdcc_chart caption="Revenue growth by region" label="fig:revenue-growth"
        frame = pd.DataFrame({"quarter": ["Q1"], "revenue": [10]})
        alt.Chart(frame).mark_bar().encode(x="quarter", y="revenue")
        ```
        """,
    )
    output_path = tmp_path / "invalid-reference.pdf"

    with pytest.raises(ValidationError) as exc_info:
        run_compile(
            CompileOptions(
                input_path=source,
                output_path=output_path,
            )
        )

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.stage.value == "validation"
    assert diagnostic.message == "unresolved reference: fig:not-found"
    assert not output_path.exists()
    assert not (tmp_path / BUILD_DIR_NAME).exists()


def test_compile_rejects_duplicate_cross_reference_labels_during_validation(
    tmp_path: Path,
) -> None:
    source = _write_source(
        tmp_path,
        """
        ```mdcc_chart caption="Revenue growth by region" label="fig:revenue-growth"
        frame = pd.DataFrame({"quarter": ["Q1"], "revenue": [10]})
        alt.Chart(frame).mark_bar().encode(x="quarter", y="revenue")
        ```

        ```mdcc_chart caption="Revenue growth by product" label="fig:revenue-growth"
        frame = pd.DataFrame({"quarter": ["Q1"], "revenue": [10]})
        alt.Chart(frame).mark_bar().encode(x="quarter", y="revenue")
        ```
        """,
    )
    output_path = tmp_path / "duplicate-labels.pdf"

    with pytest.raises(ValidationError) as exc_info:
        run_compile(
            CompileOptions(
                input_path=source,
                output_path=output_path,
            )
        )

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.stage.value == "validation"
    assert diagnostic.message == "duplicate label: fig:revenue-growth"
    assert not output_path.exists()
    assert not (tmp_path / BUILD_DIR_NAME).exists()


def test_compile_rejects_import_policy_during_validation(tmp_path: Path) -> None:
    source = _write_source(
        tmp_path,
        """
        ```mdcc_table
        import os
        pd.DataFrame({"cwd": [os.getcwd()]})
        ```
        """,
    )
    output_path = tmp_path / "import-policy.pdf"

    with pytest.raises(ValidationError) as exc_info:
        run_compile(
            CompileOptions(
                input_path=source,
                output_path=output_path,
            )
        )

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.stage.value == "validation"
    assert diagnostic.message == "user imports are not allowed in executable blocks"
    assert diagnostic.block_id == "block-0001"
    assert diagnostic.block_index == 0
    assert diagnostic.source_snippet == "import os"
    assert not output_path.exists()
    assert not (tmp_path / BUILD_DIR_NAME).exists()


def test_compile_does_not_reject_phase_two_metadata_key_in_parser(
    tmp_path: Path,
) -> None:
    source = _write_source(
        tmp_path,
        """
        ```mdcc_chart caption="Revenue" width="wide"
        chart
        ```
        """,
    )

    try:
        run_compile(
            CompileOptions(
                input_path=source,
                output_path=tmp_path / "ignored.pdf",
            )
        )
    except ValidationError:
        pass
    except ParseError as exc:  # pragma: no cover - regression guard
        pytest.fail(f"metadata key should fail in validation, not parsing: {exc}")


def test_compile_propagates_execution_failure_before_later_stages(
    tmp_path: Path,
) -> None:
    source = _write_source(
        tmp_path,
        """
        # Runtime failure

        ```mdcc_table
        raise RuntimeError("boom")
        ```
        """,
    )
    output_path = tmp_path / "failed.pdf"

    with pytest.raises(ExecutionError) as exc_info:
        run_compile(
            CompileOptions(
                input_path=source,
                output_path=output_path,
            )
        )

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.message == "block execution failed"
    assert diagnostic.block_id == "block-0001"
    assert diagnostic.block_index == 0
    assert diagnostic.source_path == source
    assert "RuntimeError: boom" in (diagnostic.stderr or "")
    assert not output_path.exists()
    assert not (tmp_path / BUILD_DIR_NAME).exists()
