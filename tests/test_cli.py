"""CLI wiring tests for the mdcc compile command."""

from __future__ import annotations

from pathlib import Path
import textwrap
from unittest.mock import patch

from typer.testing import CliRunner

from mdcc import __version__
from mdcc.bundle.commands import (
    BundleCreateOptions,
    create_bundle as real_create_bundle,
)
from mdcc.cli import app
from mdcc.errors import ErrorContext, InspectionError, MdccError, ReadError
from mdcc.compile import CompileOptions
from mdcc.models import (
    BlockType,
    Diagnostic,
    DiagnosticCategory,
    DiagnosticStage,
    SourceLocation,
    SourcePosition,
    SourceSpan,
)


def _write_source(tmp_path: Path, body: str) -> Path:
    source = tmp_path / "report.md"
    source.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return source


# ---------------------------------------------------------------------------
# Argument handling
# ---------------------------------------------------------------------------


def test_compile_no_args_shows_help(cli_runner: CliRunner) -> None:
    """Invoking ``mdcc`` without arguments shows help."""
    result = cli_runner.invoke(app, [])
    # Typer shows help text; exit code may vary based on version.
    assert "compile" in result.output.lower() or "usage" in result.output.lower()


def test_compile_requires_input_argument(cli_runner: CliRunner) -> None:
    """``mdcc compile`` without an input file should fail."""
    result = cli_runner.invoke(app, ["compile"])
    assert result.exit_code != 0


def test_validate_requires_input_argument(cli_runner: CliRunner) -> None:
    """``mdcc validate`` without an input file should fail."""
    result = cli_runner.invoke(app, ["validate"])
    assert result.exit_code != 0


def test_compile_rejects_nonexistent_input(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    """Providing a file that does not exist should fail with a clear error."""
    result = cli_runner.invoke(app, ["compile", str(tmp_path / "missing.md")])
    assert result.exit_code != 0


def test_validate_rejects_nonexistent_input(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    """Providing a missing file to ``mdcc validate`` should fail."""
    result = cli_runner.invoke(app, ["validate", str(tmp_path / "missing.md")])
    assert result.exit_code != 0


def test_compile_generates_default_output_path(
    cli_runner: CliRunner, tmp_source_file: Path
) -> None:
    """Omitting the output argument should default to ``<input>.pdf``."""
    captured_options: list[CompileOptions] = []

    def _capture(options: CompileOptions) -> None:
        captured_options.append(options)

    with patch("mdcc.cli.run_compile", side_effect=_capture):
        result = cli_runner.invoke(app, ["compile", str(tmp_source_file)])

    assert result.exit_code == 0
    assert len(captured_options) == 1
    assert captured_options[0].output_path == tmp_source_file.with_suffix(".pdf")


def test_compile_accepts_explicit_output_path(
    cli_runner: CliRunner, tmp_source_file: Path, tmp_path: Path
) -> None:
    """Both input and output arguments are forwarded correctly."""
    explicit_output = tmp_path / "result.pdf"
    captured_options: list[CompileOptions] = []

    def _capture(options: CompileOptions) -> None:
        captured_options.append(options)

    with patch("mdcc.cli.run_compile", side_effect=_capture):
        result = cli_runner.invoke(
            app, ["compile", str(tmp_source_file), str(explicit_output)]
        )

    assert result.exit_code == 0
    assert len(captured_options) == 1
    assert captured_options[0].output_path == explicit_output


# ---------------------------------------------------------------------------
# Option forwarding
# ---------------------------------------------------------------------------


def test_compile_passes_timeout_option(
    cli_runner: CliRunner, tmp_source_file: Path
) -> None:
    """``--timeout 60`` should be forwarded to CompileOptions."""
    captured_options: list[CompileOptions] = []

    def _capture(options: CompileOptions) -> None:
        captured_options.append(options)

    with patch("mdcc.cli.run_compile", side_effect=_capture):
        result = cli_runner.invoke(
            app, ["compile", str(tmp_source_file), "--timeout", "60"]
        )

    assert result.exit_code == 0
    assert captured_options[0].timeout_seconds == 60.0


def test_compile_passes_keep_build_dir_flag(
    cli_runner: CliRunner, tmp_source_file: Path
) -> None:
    """``--keep-build-dir`` should set the flag to True."""
    captured_options: list[CompileOptions] = []

    def _capture(options: CompileOptions) -> None:
        captured_options.append(options)

    with patch("mdcc.cli.run_compile", side_effect=_capture):
        result = cli_runner.invoke(
            app, ["compile", str(tmp_source_file), "--keep-build-dir"]
        )

    assert result.exit_code == 0
    assert captured_options[0].keep_build_dir is True


def test_compile_passes_no_cache_flag(
    cli_runner: CliRunner, tmp_source_file: Path
) -> None:
    """``--no-cache`` should disable the block cache."""
    captured_options: list[CompileOptions] = []

    def _capture(options: CompileOptions) -> None:
        captured_options.append(options)

    with patch("mdcc.cli.run_compile", side_effect=_capture):
        result = cli_runner.invoke(app, ["compile", str(tmp_source_file), "--no-cache"])

    assert result.exit_code == 0
    assert captured_options[0].use_cache is False


def test_compile_passes_verbose_flag(
    cli_runner: CliRunner, tmp_source_file: Path
) -> None:
    """``-v`` / ``--verbose`` should set the verbose flag."""
    captured_options: list[CompileOptions] = []

    def _capture(options: CompileOptions) -> None:
        captured_options.append(options)

    with patch("mdcc.cli.run_compile", side_effect=_capture):
        result = cli_runner.invoke(app, ["compile", str(tmp_source_file), "--verbose"])

    assert result.exit_code == 0
    assert captured_options[0].verbose is True


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


def test_version_flag(cli_runner: CliRunner) -> None:
    """``mdcc --version`` should print the current version."""
    result = cli_runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


# ---------------------------------------------------------------------------
# Error surfaces
# ---------------------------------------------------------------------------


def test_compile_surfaces_mdcc_error(
    cli_runner: CliRunner, tmp_source_file: Path
) -> None:
    """An ``MdccError`` during compilation should be presented and exit 1."""
    diagnostic = Diagnostic(
        stage=DiagnosticStage.PARSE,
        category=DiagnosticCategory.PARSE_ERROR,
        message="unclosed fenced block",
        source_path=tmp_source_file,
    )
    error = MdccError(diagnostic)

    with patch("mdcc.cli.run_compile", side_effect=error):
        result = cli_runner.invoke(app, ["compile", str(tmp_source_file)])

    assert result.exit_code == 1
    assert "unclosed fenced block" in result.output
    assert "stage: parse" in result.output
    assert f"file: {tmp_source_file}" in result.output


def test_compile_formats_diagnostic_context_for_humans(
    cli_runner: CliRunner, tmp_source_file: Path
) -> None:
    diagnostic = Diagnostic(
        stage=DiagnosticStage.VALIDATION,
        category=DiagnosticCategory.VALIDATION_ERROR,
        message="table output type mismatch",
        source_path=tmp_source_file,
        block_id="block-0002",
        block_type=BlockType.TABLE,
        block_index=1,
        location=SourceLocation(
            source_path=tmp_source_file,
            span=SourceSpan(
                start=SourcePosition(line=12, column=1),
                end=SourcePosition(line=15, column=3),
            ),
        ),
        source_snippet="```mdcc_table\n42\n```",
    )
    error = MdccError(diagnostic)

    with patch("mdcc.cli.run_compile", side_effect=error):
        result = cli_runner.invoke(app, ["compile", str(tmp_source_file)])

    assert result.exit_code == 1
    assert "block: #1 block-0002 (mdcc_table)" in result.output
    assert "location: lines 12:1-15:3" in result.output
    assert "snippet:" in result.output


def test_compile_verbose_includes_diagnostic_details(
    cli_runner: CliRunner, tmp_source_file: Path
) -> None:
    diagnostic = Diagnostic(
        stage=DiagnosticStage.EXECUTION,
        category=DiagnosticCategory.EXECUTION_ERROR,
        message="block execution failed",
        source_path=tmp_source_file,
        stderr="traceback line",
        stdout="debug print",
        exception_type="RuntimeError",
        exception_message="boom",
    )
    error = MdccError(diagnostic)

    with patch("mdcc.cli.run_compile", side_effect=error):
        result = cli_runner.invoke(app, ["compile", str(tmp_source_file), "--verbose"])

    assert result.exit_code == 1
    assert "category: execution_error" in result.output
    assert "stderr: traceback line" in result.output
    assert "stdout: debug print" in result.output
    assert "caused by: RuntimeError: boom" in result.output


def test_compile_surfaces_unexpected_error(
    cli_runner: CliRunner, tmp_source_file: Path
) -> None:
    """An unhandled exception should produce a generic error and exit 1."""
    with patch("mdcc.cli.run_compile", side_effect=RuntimeError("boom")):
        result = cli_runner.invoke(app, ["compile", str(tmp_source_file)])

    assert result.exit_code == 1
    assert "unexpected failure" in result.output
    assert "boom" in result.output


def test_compile_verbose_surfaces_unexpected_error_stage(
    cli_runner: CliRunner, tmp_source_file: Path
) -> None:
    with patch("mdcc.cli.run_compile", side_effect=RuntimeError("boom")):
        result = cli_runner.invoke(app, ["compile", str(tmp_source_file), "--verbose"])

    assert result.exit_code == 1
    assert "stage: internal" in result.output


# ---------------------------------------------------------------------------
# validate command behavior
# ---------------------------------------------------------------------------


def test_validate_reports_successful_document(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    source = _write_source(
        tmp_path,
        """
        ---
        title: Revenue Report
        ---

        Intro text.

        ```mdcc_chart caption="Revenue by region" label="fig:revenue-region"
        frame = pd.DataFrame({"quarter": ["Q1"], "revenue": [10]})
        alt.Chart(frame).mark_bar().encode(x="quarter", y="revenue")
        ```

        ```mdcc_table label="tbl:regional-summary"
        pd.DataFrame({"region": ["na"], "revenue": [10]})
        ```
        """,
    )

    result = cli_runner.invoke(app, ["validate", str(source)])

    assert result.exit_code == 0
    assert "Validation successful" in result.output
    assert "Blocks discovered:" in result.output
    assert "1. mdcc_chart (line 4)" in result.output
    assert "2. mdcc_table (line 9)" in result.output
    assert "Labels:" in result.output
    assert "- fig:revenue-region" in result.output
    assert "- tbl:regional-summary" in result.output


def test_validate_reports_warnings_without_failing(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    source = _write_source(
        tmp_path,
        """
        ---
        title: Revenue Report
        team: finance
        ---

        # Intro
        """,
    )

    result = cli_runner.invoke(app, ["validate", str(source)])

    assert result.exit_code == 0
    assert "Validation successful" in result.output
    assert "Warnings:" in result.output
    assert "unknown frontmatter fields were preserved in extra" in result.output
    assert "Blocks discovered:\n- none" in result.output
    assert "Labels:\n- none" in result.output


def test_validate_reports_duplicate_labels(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    source = _write_source(
        tmp_path,
        """
        ```mdcc_chart label="fig:revenue-growth"
        frame = pd.DataFrame({"quarter": ["Q1"], "revenue": [10]})
        alt.Chart(frame).mark_bar().encode(x="quarter", y="revenue")
        ```

        ```mdcc_chart label="fig:revenue-growth"
        frame = pd.DataFrame({"quarter": ["Q2"], "revenue": [12]})
        alt.Chart(frame).mark_bar().encode(x="quarter", y="revenue")
        ```
        """,
    )

    result = cli_runner.invoke(app, ["validate", str(source)])

    assert result.exit_code == 1
    assert "Validation failed" in result.output
    assert "Errors:" in result.output
    assert "duplicate label: fig:revenue-growth" in result.output
    assert "lines 6:1-9:3" in result.output
    assert "Blocks discovered:" not in result.output


def test_validate_reports_unresolved_references(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    source = _write_source(
        tmp_path,
        """
        See @fig:not-found for details.

        ```mdcc_chart label="fig:revenue-growth"
        frame = pd.DataFrame({"quarter": ["Q1"], "revenue": [10]})
        alt.Chart(frame).mark_bar().encode(x="quarter", y="revenue")
        ```
        """,
    )

    result = cli_runner.invoke(app, ["validate", str(source)])

    assert result.exit_code == 1
    assert "unresolved reference: fig:not-found" in result.output
    assert "lines 1:1-2:1" in result.output


def test_validate_reports_invalid_python_syntax(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    source = _write_source(
        tmp_path,
        """
        ```mdcc_table
        if True print("boom")
        ```
        """,
    )

    result = cli_runner.invoke(app, ["validate", str(source)])

    assert result.exit_code == 1
    assert "executable block contains invalid Python syntax" in result.output
    assert "line 2:9" in result.output


def test_validate_reports_import_policy_violation(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    source = _write_source(
        tmp_path,
        """
        ```mdcc_table
        import os
        pd.DataFrame({"cwd": [os.getcwd()]})
        ```
        """,
    )

    result = cli_runner.invoke(app, ["validate", str(source)])

    assert result.exit_code == 1
    assert "user imports are not allowed in executable blocks" in result.output
    assert "line 2:1-9" in result.output


def test_validate_reports_dynamic_import_policy_violation(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    source = _write_source(
        tmp_path,
        """
        ```mdcc_table
        module = __import__("os")
        pd.DataFrame({"module": [module.__name__]})
        ```
        """,
    )

    result = cli_runner.invoke(app, ["validate", str(source)])

    assert result.exit_code == 1
    assert "dynamic imports are not allowed in executable blocks" in result.output
    assert "line 2:10-25" in result.output


def test_validate_surfaces_parse_errors_with_existing_diagnostics(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    source = _write_source(
        tmp_path,
        """
        ---
        title: broken
        """,
    )

    result = cli_runner.invoke(app, ["validate", str(source)])

    assert result.exit_code == 1
    assert "error: frontmatter opening delimiter is not closed" in result.output
    assert "stage: parse" in result.output


def test_validate_surfaces_malformed_block_headers_with_existing_diagnostics(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    source = _write_source(
        tmp_path,
        """
        ```mdcc_chart caption="Revenue"label="fig:revenue"
        chart
        ```
        """,
    )

    result = cli_runner.invoke(app, ["validate", str(source)])

    assert result.exit_code == 1
    assert "error: malformed executable block metadata attributes" in result.output
    assert "stage: parse" in result.output


def test_bundle_create_generates_default_output_path(
    cli_runner: CliRunner, tmp_source_file: Path
) -> None:
    captured_options: list[BundleCreateOptions] = []

    def _capture(options: BundleCreateOptions) -> None:
        captured_options.append(options)

    with patch("mdcc.cli.create_bundle", side_effect=_capture):
        result = cli_runner.invoke(app, ["bundle", "create", str(tmp_source_file)])

    assert result.exit_code == 0
    assert len(captured_options) == 1
    assert captured_options[0].output_path == tmp_source_file.with_suffix(".mdcx")


def test_dataset_commands_round_trip_bundle(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    data_path = tmp_path / "data.csv"
    data_path.write_text("region,revenue\nna,10\neu,20\n", encoding="utf-8")
    source = _write_source(
        tmp_path,
        """
        ```mdcc_table
        frame = pd.read_csv("data.csv")
        frame
        ```
        """,
    )
    bundle_path = real_create_bundle(
        BundleCreateOptions(
            input_path=source,
            output_path=tmp_path / "report.mdcx",
        )
    )

    list_result = cli_runner.invoke(app, ["dataset", "list", str(bundle_path)])
    assert list_result.exit_code == 0
    assert "ds_block_0001_primary" in list_result.output

    show_result = cli_runner.invoke(
        app,
        ["dataset", "show", str(bundle_path), "--id", "dset_001"],
    )
    assert show_result.exit_code == 0
    assert "role_summary: input,primary" in show_result.output

    head_result = cli_runner.invoke(
        app,
        ["dataset", "head", str(bundle_path), "--id", "dset_001", "--rows", "1"],
    )
    assert head_result.exit_code == 0
    assert "na" in head_result.output


def test_sql_command_rejects_file_option(cli_runner: CliRunner, tmp_path: Path) -> None:
    bundle_file = tmp_path / "report.mdcx"
    bundle_file.write_text("not-a-bundle", encoding="utf-8")
    query_file = tmp_path / "query.sql"
    query_file.write_text("select 1", encoding="utf-8")

    result = cli_runner.invoke(
        app,
        ["sql", str(bundle_file), "select 1", "--file", str(query_file)],
    )

    assert result.exit_code == 1
    assert "SQL file input is not supported" in result.output


def test_bundle_create_surfaces_read_error(
    cli_runner: CliRunner, tmp_source_file: Path
) -> None:
    error = ReadError.from_message(
        "failed to read source file",
        context=ErrorContext(source_path=tmp_source_file),
    )

    with patch("mdcc.cli.create_bundle", side_effect=error):
        result = cli_runner.invoke(app, ["bundle", "create", str(tmp_source_file)])

    assert result.exit_code == 1
    assert "failed to read source file" in result.output
    assert "stage: read" in result.output
    assert f"file: {tmp_source_file}" in result.output


def test_inspect_command_round_trips_bundle_views(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    data_path = tmp_path / "data.csv"
    data_path.write_text("region,revenue\nna,10\neu,20\n", encoding="utf-8")
    source = _write_source(
        tmp_path,
        """
        # Revenue

        ```mdcc_table
        frame = pd.read_csv("data.csv")
        frame
        ```
        """,
    )
    bundle_path = real_create_bundle(
        BundleCreateOptions(
            input_path=source,
            output_path=tmp_path / "report.mdcx",
        )
    )

    overview_result = cli_runner.invoke(app, ["inspect", str(bundle_path)])
    assert overview_result.exit_code == 0
    assert "block details:" in overview_result.output
    assert "dataset details:" in overview_result.output

    source_result = cli_runner.invoke(app, ["inspect", str(bundle_path), "--source"])
    assert source_result.exit_code == 0
    assert source_result.output == source.read_text(encoding="utf-8")

    annotated_result = cli_runner.invoke(
        app, ["inspect", str(bundle_path), "--annotated"]
    )
    assert annotated_result.exit_code == 0
    assert (
        "<!-- mdcc-inspect:block id=block-0001 type=mdcc_table -->"
        in annotated_result.output
    )


def test_inspect_command_rejects_conflicting_projection_flags(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    bundle_file = tmp_path / "report.mdcx"
    bundle_file.write_text("not-a-bundle", encoding="utf-8")

    result = cli_runner.invoke(
        app, ["inspect", str(bundle_file), "--source", "--annotated"]
    )

    assert result.exit_code != 0
    assert "--source and --annotated cannot be used together" in result.output


def test_inspect_command_surfaces_mdcc_error(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    bundle_file = tmp_path / "report.mdcx"
    bundle_file.write_text("placeholder", encoding="utf-8")
    error = InspectionError.from_message(
        "cannot project annotated source",
        context=ErrorContext(source_path=bundle_file),
    )

    with patch("mdcc.cli.inspect_bundle_annotated", side_effect=error):
        result = cli_runner.invoke(app, ["inspect", str(bundle_file), "--annotated"])

    assert result.exit_code == 1
    assert "cannot project annotated source" in result.output
    assert "stage: inspection" in result.output
    assert f"file: {bundle_file}" in result.output
