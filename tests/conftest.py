"""Shared pytest fixtures for mdcc tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture()
def cli_runner() -> CliRunner:
    """Provide a Typer test runner that captures output."""
    return CliRunner()


@pytest.fixture()
def tmp_source_file(tmp_path: Path) -> Path:
    """Create a minimal valid markdown source file in a temp directory."""
    source = tmp_path / "report.md"
    source.write_text(
        "---\ntitle: Test Report\n---\n\n# Introduction\n\nHello, world.\n",
        encoding="utf-8",
    )
    return source
