"""CLI entrypoint for the mdcc executable report compiler.

Provides the ``mdcc compile`` and ``mdcc validate`` commands for full
compilation and pre-execution document validation.
"""

from __future__ import annotations
from pathlib import Path
from typing import Annotated, Optional

import typer

from mdcc import __version__
from mdcc.bundle.commands import (
    BundleCreateOptions,
    bundle_info,
    render_bundle_to_path,
    bundle_validate,
    create_bundle,
    dataset_head_table,
    dataset_list_table,
    dataset_schema_table,
    dataset_show,
    extract_dataset_to_path,
    extract_source_to_path,
    inspect_bundle_annotated,
    inspect_bundle_overview,
    inspect_bundle_source,
    sql_query_table,
)
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
bundle_app = typer.Typer(name="bundle", help="Create and inspect mdcc bundles.")
dataset_app = typer.Typer(name="dataset", help="Inspect persisted datasets.")
extract_app = typer.Typer(name="extract", help="Extract bundle contents.")
app.add_typer(bundle_app)
app.add_typer(dataset_app)
app.add_typer(extract_app)


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

BundleFileArgument = Annotated[
    Path,
    typer.Argument(
        help="Path to the bundle file.",
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


def _resolve_bundle_output_path(input_path: Path, output: Path | None) -> Path:
    if output is not None:
        return output
    return input_path.with_suffix(".mdcx")


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


@app.command()
def render(
    bundle_file: BundleFileArgument,
    output_file: Annotated[
        Path,
        typer.Option("--output", "-o", help="Path to the output PDF file."),
    ],
) -> None:
    """Render a bundle into a PDF report."""
    try:
        render_bundle_to_path(bundle_file, output_file)
    except MdccError as exc:
        _report_mdcc_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _report_unexpected_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc


@bundle_app.command("create")
def bundle_create(
    input_file: InputFileArgument,
    output_file: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Path to the output bundle file."),
    ] = None,
    timeout: Annotated[
        float,
        typer.Option(
            "--timeout", "-t", help="Per-block execution timeout in seconds.", min=1
        ),
    ] = 30.0,
    keep_build_dir: Annotated[
        bool,
        typer.Option(
            "--keep-build-dir",
            help="Preserve the .mdcc_build/ directory after bundle creation.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose diagnostic output."),
    ] = False,
) -> None:
    resolved_output = _resolve_bundle_output_path(input_file, output_file)
    options = BundleCreateOptions(
        input_path=input_file,
        output_path=resolved_output,
        timeout_seconds=timeout,
        keep_build_dir=keep_build_dir,
        verbose=verbose,
    )
    try:
        create_bundle(options)
    except MdccError as exc:
        _report_mdcc_error(exc, verbose=verbose)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _report_unexpected_error(exc, verbose=verbose)
        raise typer.Exit(code=1) from exc

    if verbose:
        typer.echo(f"✓ bundled {input_file.name} → {resolved_output}")


@bundle_app.command("info")
def bundle_info_command(bundle_file: BundleFileArgument) -> None:
    try:
        typer.echo(bundle_info(bundle_file))
    except MdccError as exc:
        _report_mdcc_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _report_unexpected_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc


@bundle_app.command("validate")
def bundle_validate_command(bundle_file: BundleFileArgument) -> None:
    try:
        typer.echo(bundle_validate(bundle_file))
    except MdccError as exc:
        _report_mdcc_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _report_unexpected_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc


@app.command("inspect")
def inspect_command(
    bundle_file: BundleFileArgument,
    source: Annotated[
        bool,
        typer.Option(
            "--source", help="Print the canonical source stored in the bundle."
        ),
    ] = False,
    annotated: Annotated[
        bool,
        typer.Option(
            "--annotated",
            help="Print a derived annotated source view with dataset overlays.",
        ),
    ] = False,
) -> None:
    if source and annotated:
        raise typer.BadParameter("--source and --annotated cannot be used together.")

    try:
        if source:
            typer.echo(inspect_bundle_source(bundle_file), nl=False)
            return
        if annotated:
            typer.echo(inspect_bundle_annotated(bundle_file), nl=False)
            return
        typer.echo(inspect_bundle_overview(bundle_file))
    except MdccError as exc:
        _report_mdcc_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _report_unexpected_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc


@dataset_app.command("list")
def dataset_list(bundle_file: BundleFileArgument) -> None:
    try:
        typer.echo(dataset_list_table(bundle_file))
    except MdccError as exc:
        _report_mdcc_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _report_unexpected_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc


@dataset_app.command("show")
def dataset_show_command(
    bundle_file: BundleFileArgument,
    dataset_id: Annotated[str, typer.Option("--id", help="Dataset identifier.")],
) -> None:
    try:
        typer.echo(dataset_show(bundle_file, dataset_id))
    except MdccError as exc:
        _report_mdcc_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _report_unexpected_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc


@dataset_app.command("schema")
def dataset_schema_command(
    bundle_file: BundleFileArgument,
    dataset_id: Annotated[str, typer.Option("--id", help="Dataset identifier.")],
) -> None:
    try:
        typer.echo(dataset_schema_table(bundle_file, dataset_id))
    except MdccError as exc:
        _report_mdcc_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _report_unexpected_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc


@dataset_app.command("head")
def dataset_head_command(
    bundle_file: BundleFileArgument,
    dataset_id: Annotated[str, typer.Option("--id", help="Dataset identifier.")],
    rows: Annotated[
        int, typer.Option("--rows", help="Number of rows to preview.", min=1)
    ] = 5,
) -> None:
    try:
        typer.echo(dataset_head_table(bundle_file, dataset_id, rows))
    except MdccError as exc:
        _report_mdcc_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _report_unexpected_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc


@extract_app.command("source")
def extract_source_command(
    bundle_file: BundleFileArgument,
    output_file: Annotated[
        Path, typer.Option("--output", "-o", help="Output source path.")
    ],
) -> None:
    try:
        extract_source_to_path(bundle_file, output_file)
    except MdccError as exc:
        _report_mdcc_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _report_unexpected_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc


@extract_app.command("dataset")
def extract_dataset_command(
    bundle_file: BundleFileArgument,
    dataset_id: Annotated[str, typer.Option("--id", help="Dataset identifier.")],
    output_file: Annotated[
        Path, typer.Option("--output", "-o", help="Output dataset CSV path.")
    ],
) -> None:
    try:
        extract_dataset_to_path(bundle_file, dataset_id, output_file)
    except MdccError as exc:
        _report_mdcc_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _report_unexpected_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc


@app.command("sql")
def sql_command(
    bundle_file: BundleFileArgument,
    query: Annotated[
        str, typer.Argument(help="SQL query to execute against the bundle.")
    ],
    file: Annotated[
        Optional[Path],
        typer.Option("--file", help="Unsupported: SQL file input."),
    ] = None,
) -> None:
    if file is not None:
        typer.echo(
            "error: unsupported option: SQL file input is not supported; pass the SQL query as a string argument",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        typer.echo(sql_query_table(bundle_file, query))
    except MdccError as exc:
        _report_mdcc_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _report_unexpected_error(exc, verbose=False)
        raise typer.Exit(code=1) from exc


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
