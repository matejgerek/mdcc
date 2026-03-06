import typer

app = typer.Typer(help="mdcc: Agent-First Executable Report Compiler")


@app.command()
def compile_report(
    input_file: str = typer.Argument(..., help="Path to the source markdown file"),
    output_file: str = typer.Argument(..., help="Path to the output PDF file"),
):
    """
    Compile a markdown report into a PDF.
    """
    typer.echo(f"Compiling {input_file} to {output_file}...")
    # TODO: Orchestrate compiling pipeline (read, parse, run, render, export) [T20]


if __name__ == "__main__":
    app()
