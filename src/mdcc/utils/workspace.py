"""Temporary build directory and artifact management.

Provides a ``BuildContext`` that creates and manages the ``.mdcc_build/``
directory adjacent to the source file.  Downstream pipeline stages
(executor, renderers) use its path helpers to write intermediate artifacts
into a well-structured, deterministic namespace.

The context manager protocol ensures cleanup on success (unless the caller
opts to preserve the directory via ``keep=True``).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Sub-directory names inside the build root.
_CHARTS_DIR = "charts"
_TABLES_DIR = "tables"
_PAYLOADS_DIR = "payloads"
_LOGS_DIR = "logs"
_RESULTS_DIR = "results"

# Default name of the build directory placed next to the source file.
BUILD_DIR_NAME = ".mdcc_build"


class BuildContext:
    """Manages the temporary build directory for a single compilation run.

    Usage::

        ctx = BuildContext.create(source_path, keep=False)
        with ctx:
            chart_img = ctx.chart_path(0, ".png")
            # … renderer writes to chart_img …

    On context-manager exit the entire ``.mdcc_build/`` tree is removed
    unless ``keep=True``.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, build_dir: Path, *, keep: bool = False) -> None:
        self._build_dir = build_dir
        self._keep = keep

    @classmethod
    def create(cls, source_path: Path, *, keep: bool = False) -> BuildContext:
        """Create (or re-use) the build directory next to *source_path*.

        Parameters
        ----------
        source_path:
            Absolute path to the source ``.md`` file being compiled.
        keep:
            If ``True`` the build directory will **not** be removed when the
            context manager exits.

        Returns
        -------
        BuildContext
            A ready-to-use context whose sub-directories already exist.
        """
        build_dir = source_path.parent / BUILD_DIR_NAME
        build_dir.mkdir(parents=True, exist_ok=True)

        for sub in (_CHARTS_DIR, _TABLES_DIR, _PAYLOADS_DIR, _LOGS_DIR, _RESULTS_DIR):
            (build_dir / sub).mkdir(exist_ok=True)

        return cls(build_dir, keep=keep)

    # ------------------------------------------------------------------
    # Read-only accessors
    # ------------------------------------------------------------------

    @property
    def build_dir(self) -> Path:
        """Root of the build directory (``.mdcc_build/``)."""
        return self._build_dir

    @property
    def charts_dir(self) -> Path:
        """Directory for rendered chart image artifacts."""
        return self._build_dir / _CHARTS_DIR

    @property
    def tables_dir(self) -> Path:
        """Directory for rendered table artifacts."""
        return self._build_dir / _TABLES_DIR

    @property
    def payloads_dir(self) -> Path:
        """Directory for execution payload scripts."""
        return self._build_dir / _PAYLOADS_DIR

    @property
    def logs_dir(self) -> Path:
        """Directory for block execution logs."""
        return self._build_dir / _LOGS_DIR

    @property
    def results_dir(self) -> Path:
        """Directory for reserved execution result envelopes."""
        return self._build_dir / _RESULTS_DIR

    # ------------------------------------------------------------------
    # Path helpers — deterministic file names per block index
    # ------------------------------------------------------------------

    def chart_path(self, block_index: int, ext: str = ".png") -> Path:
        """Return the target path for a rendered chart artifact.

        Parameters
        ----------
        block_index:
            Zero-based index of the executable block.
        ext:
            File extension including the leading dot (default ``".png"``).
        """
        return self.charts_dir / f"chart_{block_index:03d}{ext}"

    def table_path(self, block_index: int, ext: str = ".html") -> Path:
        """Return the target path for a rendered table artifact.

        Parameters
        ----------
        block_index:
            Zero-based index of the executable block.
        ext:
            File extension including the leading dot (default ``".html"``).
        """
        return self.tables_dir / f"table_{block_index:03d}{ext}"

    def payload_path(self, block_index: int) -> Path:
        """Return the target path for an execution payload script.

        Parameters
        ----------
        block_index:
            Zero-based index of the executable block.
        """
        return self.payloads_dir / f"payload_{block_index:03d}.py"

    def log_path(self, block_index: int) -> Path:
        """Return the target path for an execution log file.

        Parameters
        ----------
        block_index:
            Zero-based index of the executable block.
        """
        return self.logs_dir / f"log_{block_index:03d}.txt"

    def result_path(self, block_index: int, ext: str = ".json") -> Path:
        """Return the target path for a reserved execution result envelope.

        Parameters
        ----------
        block_index:
            Zero-based index of the executable block.
        ext:
            File extension including the leading dot (default ``".json"``).
        """
        return self.results_dir / f"result_{block_index:03d}{ext}"

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> BuildContext:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        if self._keep:
            logger.debug("keeping build directory: %s", self._build_dir)
            return

        try:
            shutil.rmtree(self._build_dir)
            logger.debug("removed build directory: %s", self._build_dir)
        except OSError:
            logger.warning(
                "failed to remove build directory: %s",
                self._build_dir,
                exc_info=True,
            )


__all__ = ["BUILD_DIR_NAME", "BuildContext"]
