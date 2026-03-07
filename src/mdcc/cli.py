"""CLI entrypoint for the mdcc executable report compiler.

Provides the ``mdcc compile`` and ``mdcc validate`` commands for full
compilation and pre-execution document validation.
"""

from __future__ import annotations
from pathlib import Path
from typing import Annotated, Optional

import typer

from mdcc import __version__
from mdcc.errors import MdccError, format_diagnostic, format_unexpected_error
from mdcc.compile import CompileOptions, compile as run_compile
from mdcc.validate import format_validation_report, validate_source_file

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="mdcc",
    help="mdcc — Agent-First Executable Report Compiler",
    add_completion=False,
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Version callback
# ---------------------------------------------------------------------------


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"mdcc {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """mdcc — Agent-First Executable Report Compiler."""


# ---------------------------------------------------------------------------
# shared CLI argument builders
# ---------------------------------------------------------------------------


InputFileArgument = Annotated[
    Path,
    typer.Argument(
        help="Path to the source markdown file.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
]


def _resolve_output_path(input_path: Path, output: Path | None) -> Path:
    """Derive the output PDF path when the user omits it."""
    if output is not None:
        return output
    return input_path.with_suffix(".pdf")


# ---------------------------------------------------------------------------
# compile command
# ---------------------------------------------------------------------------


@app.command()
def compile(
    input_file: InputFileArgument,
    output_file: Annotated[
        Optional[Path],
        typer.Argument(
            help="Path to the output PDF file.  "
            "Defaults to <input>.pdf in the same directory.",
        ),
    ] = None,
    timeout: Annotated[
        float,
        typer.Option(
            "--timeout",
            "-t",
            help="Per-block execution timeout in seconds.",
            min=1,
        ),
    ] = 30.0,
    keep_build_dir: Annotated[
        bool,
        typer.Option(
            "--keep-build-dir",
            help="Preserve the .mdcc_build/ directory after compilation.",
        ),
    ] = False,
    no_cache: Annotated[
        bool,
        typer.Option(
            "--no-cache",
            help="Disable the block cache and force fresh execution.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable verbose diagnostic output.",
        ),
    ] = False,
) -> None:
    """Compile a markdown source file into a PDF report."""
    resolved_output = _resolve_output_path(input_file, output_file)

    options = CompileOptions(
        input_path=input_file,
        output_path=resolved_output,
        timeout_seconds=timeout,
        keep_build_dir=keep_build_dir,
        use_cache=not no_cache,
        verbose=verbose,
    )

    try:
        run_compile(options)
    except MdccError as exc:
        _report_mdcc_error(exc, verbose=verbose)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _report_unexpected_error(exc, verbose=verbose)
        raise typer.Exit(code=1) from exc

    if verbose:
        typer.echo(f"✓ compiled {input_file.name} → {resolved_output}")


# ---------------------------------------------------------------------------
# validate command
# ---------------------------------------------------------------------------


@app.command()
def validate(input_file: InputFileArgument) -> None:
    """Validate a markdown source file without executing blocks."""
    try:
        document, result = validate_source_file(input_file)
    except MdccError as exc:
        _report_mdcc_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _report_unexpected_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc

    report = format_validation_report(document, result)
    if result.ok:
        typer.echo(report)
        return

    typer.echo(report, err=True)
    raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Error presentation helpers
# ---------------------------------------------------------------------------


def _report_mdcc_error(exc: MdccError, *, verbose: bool) -> None:
    """Format a compiler error for the terminal."""
    typer.echo(format_diagnostic(exc.diagnostic, verbose=verbose), err=True)


def _report_unexpected_error(exc: Exception, *, verbose: bool) -> None:
    """Format an unexpected (non-MdccError) exception for the terminal."""
    typer.echo(format_unexpected_error(exc, verbose=verbose), err=True)


if __name__ == "__main__":
    app()
