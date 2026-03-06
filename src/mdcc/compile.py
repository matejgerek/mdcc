"""End-to-end compiler orchestrator.

This module will eventually coordinate the full compilation pipeline
(read → parse → validate → execute → render → assemble → PDF).

For now it exposes the CompileOptions contract and a stub entry-point
that downstream tasks (T20) will fill in.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class CompileOptions(BaseModel):
    """Resolved compilation settings forwarded from the CLI."""

    input_path: Path
    output_path: Path
    timeout_seconds: float = Field(default=30.0, gt=0)
    keep_build_dir: bool = False
    verbose: bool = False


def compile(options: CompileOptions) -> None:
    """Run the full compilation pipeline.

    Parameters
    ----------
    options:
        Resolved compile settings produced by the CLI layer.

    Raises
    ------
    NotImplementedError
        Pipeline stages are not yet wired (see T20).
    """
    raise NotImplementedError(
        "compile is not yet implemented — "
        "pipeline stages will be wired in T20"
    )
