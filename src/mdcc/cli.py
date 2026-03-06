"""CLI entrypoint for the mdcc executable report compiler.

Provides the ``mdcc compile`` command that drives the full compilation
pipeline from a single markdown source file to a PDF.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from mdcc import __version__
from mdcc.errors import MdccError
from mdcc.compile import CompileOptions, compile as run_compile

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
# compile command
# ---------------------------------------------------------------------------

def _resolve_output_path(input_path: Path, output: Path | None) -> Path:
    """Derive the output PDF path when the user omits it."""
    if output is not None:
        return output
    return input_path.with_suffix(".pdf")


@app.command()
def compile(
    input_file: Annotated[
        Path,
        typer.Argument(
            help="Path to the source markdown file.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
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
        verbose=verbose,
    )

    try:
        run_compile(options)
    except MdccError as exc:
        _report_mdcc_error(exc)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _report_unexpected_error(exc)
        raise typer.Exit(code=1) from exc

    if verbose:
        typer.echo(f"✓ compiled {input_file.name} → {resolved_output}")


# ---------------------------------------------------------------------------
# Error presentation helpers
# ---------------------------------------------------------------------------

def _report_mdcc_error(exc: MdccError) -> None:
    """Format a compiler error for the terminal."""
    diag = exc.diagnostic
    parts: list[str] = []

    parts.append(f"error: {diag.message}")

    if diag.source_path:
        loc = f"  → file: {diag.source_path}"
        if diag.block_index is not None:
            loc += f"  block #{diag.block_index}"
        if diag.block_type:
            loc += f"  ({diag.block_type})"
        parts.append(loc)

    parts.append(f"  stage: {diag.stage}")

    if diag.source_snippet:
        parts.append(f"  snippet: {diag.source_snippet}")

    if diag.stderr:
        parts.append(f"  stderr:\n{diag.stderr}")

    typer.echo("\n".join(parts), err=True)


def _report_unexpected_error(exc: Exception) -> None:
    """Format an unexpected (non-MdccError) exception for the terminal."""
    typer.echo(
        f"error: unexpected failure — {type(exc).__name__}: {exc}",
        err=True,
    )


if __name__ == "__main__":
    app()
