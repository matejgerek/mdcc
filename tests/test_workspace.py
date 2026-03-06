"""Tests for mdcc.utils.workspace — build artifact management."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mdcc.utils.workspace import BUILD_DIR_NAME, BuildContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _source_file(tmp_path: Path) -> Path:
    """Create a dummy source file inside *tmp_path*."""
    src = tmp_path / "report.md"
    src.write_text("# hello", encoding="utf-8")
    return src


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreateBuildsDirectoryStructure:
    """BuildContext.create() produces the expected directory tree."""

    def test_build_dir_exists(self, tmp_path: Path) -> None:
        src = _source_file(tmp_path)
        ctx = BuildContext.create(src)
        assert ctx.build_dir.is_dir()
        assert ctx.build_dir.name == BUILD_DIR_NAME

    def test_subdirectories_exist(self, tmp_path: Path) -> None:
        src = _source_file(tmp_path)
        ctx = BuildContext.create(src)
        assert ctx.charts_dir.is_dir()
        assert ctx.tables_dir.is_dir()
        assert ctx.payloads_dir.is_dir()
        assert ctx.logs_dir.is_dir()

    def test_build_dir_is_adjacent_to_source(self, tmp_path: Path) -> None:
        src = _source_file(tmp_path)
        ctx = BuildContext.create(src)
        assert ctx.build_dir.parent == src.parent


class TestPathHelpers:
    """Path helpers return deterministic locations under the correct sub-dir."""

    def test_chart_path(self, tmp_path: Path) -> None:
        src = _source_file(tmp_path)
        ctx = BuildContext.create(src)
        p = ctx.chart_path(0)
        assert p == ctx.charts_dir / "chart_000.png"

    def test_chart_path_custom_ext(self, tmp_path: Path) -> None:
        src = _source_file(tmp_path)
        ctx = BuildContext.create(src)
        p = ctx.chart_path(2, ext=".svg")
        assert p == ctx.charts_dir / "chart_002.svg"

    def test_table_path(self, tmp_path: Path) -> None:
        src = _source_file(tmp_path)
        ctx = BuildContext.create(src)
        p = ctx.table_path(1)
        assert p == ctx.tables_dir / "table_001.html"

    def test_payload_path(self, tmp_path: Path) -> None:
        src = _source_file(tmp_path)
        ctx = BuildContext.create(src)
        p = ctx.payload_path(5)
        assert p == ctx.payloads_dir / "payload_005.py"

    def test_log_path(self, tmp_path: Path) -> None:
        src = _source_file(tmp_path)
        ctx = BuildContext.create(src)
        p = ctx.log_path(12)
        assert p == ctx.logs_dir / "log_012.txt"


class TestContextManagerCleanup:
    """Context-manager cleans up or preserves depending on *keep*."""

    def test_removes_build_dir_when_keep_false(self, tmp_path: Path) -> None:
        src = _source_file(tmp_path)
        ctx = BuildContext.create(src, keep=False)
        build = ctx.build_dir

        with ctx:
            assert build.exists()

        assert not build.exists()

    def test_preserves_build_dir_when_keep_true(self, tmp_path: Path) -> None:
        src = _source_file(tmp_path)
        ctx = BuildContext.create(src, keep=True)
        build = ctx.build_dir

        with ctx:
            assert build.exists()

        assert build.exists()

    def test_removes_on_exception(self, tmp_path: Path) -> None:
        src = _source_file(tmp_path)
        ctx = BuildContext.create(src, keep=False)
        build = ctx.build_dir

        with pytest.raises(RuntimeError):
            with ctx:
                raise RuntimeError("boom")

        assert not build.exists()

    def test_cleanup_error_is_swallowed(self, tmp_path: Path) -> None:
        src = _source_file(tmp_path)
        ctx = BuildContext.create(src, keep=False)

        with patch("shutil.rmtree", side_effect=OSError("disk on fire")):
            # Should NOT propagate the OSError.
            with ctx:
                pass


class TestIdempotentCreate:
    """Calling create() when .mdcc_build/ already exists is safe."""

    def test_second_create_does_not_error(self, tmp_path: Path) -> None:
        src = _source_file(tmp_path)
        ctx1 = BuildContext.create(src)
        ctx2 = BuildContext.create(src)
        assert ctx1.build_dir == ctx2.build_dir
        assert ctx2.build_dir.is_dir()
