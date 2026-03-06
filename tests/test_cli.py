"""CLI wiring tests for the mdcc compile command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from mdcc import __version__
from mdcc.cli import app
from mdcc.errors import MdccError
from mdcc.compile import CompileOptions
from mdcc.models import Diagnostic, DiagnosticCategory, DiagnosticStage


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


def test_compile_rejects_nonexistent_input(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    """Providing a file that does not exist should fail with a clear error."""
    result = cli_runner.invoke(app, ["compile", str(tmp_path / "missing.md")])
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


def test_compile_surfaces_unexpected_error(
    cli_runner: CliRunner, tmp_source_file: Path
) -> None:
    """An unhandled exception should produce a generic error and exit 1."""
    with patch("mdcc.cli.run_compile", side_effect=RuntimeError("boom")):
        result = cli_runner.invoke(app, ["compile", str(tmp_source_file)])

    assert result.exit_code == 1
    assert "unexpected failure" in result.output
    assert "boom" in result.output
