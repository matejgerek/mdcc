from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from mdcc.cache import build_execution_fingerprint
from mdcc.compile import CompileOptions, compile as run_compile
from mdcc.executor.payload import build_execution_payload
from mdcc.executor.runner import run_payloads as real_run_payloads
from mdcc.models import BlockMetadata, BlockType, ExecutableBlockNode, SourceLocation
from mdcc.utils.workspace import BuildContext


def _write_source(tmp_path: Path, body: str) -> Path:
    source = tmp_path / "report.md"
    source.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return source


def _fake_pdf(*, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(
        b"%PDF-cache\n",
    )
    return output_path


def _compile_with_fake_pdf(
    *,
    input_path: Path,
    output_path: Path,
    use_cache: bool = True,
    verbose: bool = False,
) -> Path:
    with patch(
        "mdcc.compile.generate_pdf",
        side_effect=lambda intermediate, out: _fake_pdf(output_path=out),
    ):
        return run_compile(
            CompileOptions(
                input_path=input_path,
                output_path=output_path,
                use_cache=use_cache,
                verbose=verbose,
            )
        )


def _cache_manifest_path(tmp_path: Path) -> Path:
    cache_root = tmp_path / ".mdcc_cache"
    [entry_dir] = list(cache_root.iterdir())
    return entry_dir / "manifest.json"


def test_execution_fingerprint_ignores_block_index_and_metadata(tmp_path: Path) -> None:
    source = tmp_path / "report.md"
    source.write_text("# report\n", encoding="utf-8")
    build_context = BuildContext.create(source, keep=True)
    first = ExecutableBlockNode(
        node_id="block-0001",
        block_type=BlockType.TABLE,
        code='pd.DataFrame({"value": [1]})\n',
        block_index=0,
        metadata=BlockMetadata(caption="First", label="tbl:first"),
        location=SourceLocation(source_path=source),
    )
    second = ExecutableBlockNode(
        node_id="block-0009",
        block_type=BlockType.TABLE,
        code='pd.DataFrame({"value": [1]})\n',
        block_index=8,
        metadata=BlockMetadata(caption="Second", label="tbl:second"),
        location=SourceLocation(source_path=source),
    )

    first_payload = build_execution_payload(first, build_context)
    second_payload = build_execution_payload(second, build_context)

    assert build_execution_fingerprint(first_payload) == build_execution_fingerprint(
        second_payload
    )


def test_compile_reuses_cached_block_without_reexecution(tmp_path: Path) -> None:
    source = _write_source(
        tmp_path,
        """
        ```mdcc_table
        pd.DataFrame({"value": [1, 2, 3]})
        ```
        """,
    )
    first_output = tmp_path / "first.pdf"
    second_output = tmp_path / "second.pdf"

    _compile_with_fake_pdf(input_path=source, output_path=first_output)

    with patch("mdcc.compile.run_payloads", side_effect=AssertionError("re-executed")):
        result = _compile_with_fake_pdf(input_path=source, output_path=second_output)

    assert result == second_output
    assert second_output.exists()


def test_compile_invalidates_cache_when_dependency_changes(tmp_path: Path) -> None:
    data_path = tmp_path / "data.csv"
    data_path.write_text("value\n1\n2\n", encoding="utf-8")
    source = _write_source(
        tmp_path,
        """
        ```mdcc_table
        frame = pd.read_csv("data.csv")
        frame
        ```
        """,
    )

    _compile_with_fake_pdf(input_path=source, output_path=tmp_path / "first.pdf")
    data_path.write_text("value\n10\n20\n", encoding="utf-8")

    calls: list[int] = []

    def _capture(payloads, timeout_seconds):
        calls.append(len(payloads))
        return real_run_payloads(payloads, timeout_seconds)

    with patch("mdcc.compile.run_payloads", side_effect=_capture):
        _compile_with_fake_pdf(input_path=source, output_path=tmp_path / "second.pdf")

    assert calls == [1]


def test_compile_refreshes_artifact_without_reexecution_on_artifact_change(
    tmp_path: Path,
) -> None:
    source = _write_source(
        tmp_path,
        """
        ```mdcc_table
        pd.DataFrame({"value": [1, 2, 3]})
        ```
        """,
    )

    _compile_with_fake_pdf(input_path=source, output_path=tmp_path / "first.pdf")
    manifest_path = _cache_manifest_path(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_fingerprint"] = "stale-artifact"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with patch("mdcc.compile.run_payloads", side_effect=AssertionError("re-executed")):
        _compile_with_fake_pdf(input_path=source, output_path=tmp_path / "second.pdf")


def test_compile_treats_invalid_manifest_as_cache_miss(tmp_path: Path) -> None:
    source = _write_source(
        tmp_path,
        """
        ```mdcc_table
        pd.DataFrame({"value": [1, 2, 3]})
        ```
        """,
    )

    _compile_with_fake_pdf(input_path=source, output_path=tmp_path / "first.pdf")
    manifest_path = _cache_manifest_path(tmp_path)
    manifest_path.write_text("{not-json", encoding="utf-8")

    calls: list[int] = []

    def _capture(payloads, timeout_seconds):
        calls.append(len(payloads))
        return real_run_payloads(payloads, timeout_seconds)

    with patch("mdcc.compile.run_payloads", side_effect=_capture):
        _compile_with_fake_pdf(input_path=source, output_path=tmp_path / "second.pdf")

    assert calls == [1]


def test_compile_verbose_reports_cache_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _write_source(
        tmp_path,
        """
        ```mdcc_table
        pd.DataFrame({"value": [1, 2, 3]})
        ```
        """,
    )

    _compile_with_fake_pdf(
        input_path=source,
        output_path=tmp_path / "first.pdf",
        verbose=True,
    )
    first_output = capsys.readouterr().out
    assert "cache miss" in first_output

    _compile_with_fake_pdf(
        input_path=source,
        output_path=tmp_path / "second.pdf",
        verbose=True,
    )
    second_output = capsys.readouterr().out
    assert "cache hit" in second_output


def test_compile_caches_table_with_multiindex_columns(tmp_path: Path) -> None:
    source = _write_source(
        tmp_path,
        """
        ```mdcc_table
        pd.DataFrame(
            [[1, 2]],
            columns=pd.MultiIndex.from_tuples([("a", "x"), ("b", "y")]),
        )
        ```
        """,
    )

    result = _compile_with_fake_pdf(
        input_path=source,
        output_path=tmp_path / "multiindex.pdf",
    )

    assert result.exists()
    manifest = json.loads(_cache_manifest_path(tmp_path).read_text(encoding="utf-8"))
    semantic_path = (
        tmp_path
        / ".mdcc_cache"
        / manifest["execution_fingerprint"]
        / manifest["semantic_filename"]
    )
    assert manifest["semantic_filename"] == "table.pkl"
    assert pd.read_pickle(semantic_path).columns.nlevels == 2
