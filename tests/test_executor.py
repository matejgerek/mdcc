from __future__ import annotations

from pathlib import Path

import pytest

from mdcc.errors import ExecutionError, TimeoutError
from mdcc.executor.payload import build_execution_payload, build_execution_payloads
from mdcc.executor.prelude import build_runtime_prelude
from mdcc.executor.runner import run_payload, run_payloads
from mdcc.models import (
    BlockType,
    DocumentModel,
    ExecutableBlockNode,
    ExecutionStatus,
    MarkdownNode,
    SourceLocation,
    SourcePosition,
    SourceSpan,
)
from mdcc.utils.workspace import BuildContext


def _source_file(tmp_path: Path) -> Path:
    source = tmp_path / "report.md"
    source.write_text("# report\n", encoding="utf-8")
    return source


def _location(source_path: Path, line: int) -> SourceLocation:
    return SourceLocation(
        source_path=source_path,
        span=SourceSpan(
            start=SourcePosition(line=line, column=1),
            end=SourcePosition(line=line, column=10),
        ),
        snippet=f"line {line}",
    )


def _block(
    *,
    source_path: Path,
    index: int,
    code: str,
    block_type: BlockType = BlockType.TABLE,
) -> ExecutableBlockNode:
    return ExecutableBlockNode(
        node_id=f"block-{index + 1:04d}",
        block_type=block_type,
        code=code,
        block_index=index,
        location=_location(source_path, index + 1),
    )


def test_build_runtime_prelude_exposes_fixed_aliases(tmp_path: Path) -> None:
    prelude = build_runtime_prelude(tmp_path / "result_000.json")

    assert "import altair as alt" in prelude
    assert "import numpy as np" in prelude
    assert "import pandas as pd" in prelude
    assert "MDCC_RESULT_PATH" in prelude


def test_build_execution_payload_writes_deterministic_script_and_paths(
    tmp_path: Path,
) -> None:
    source = _source_file(tmp_path)
    build_context = BuildContext.create(source, keep=True)
    block = _block(source_path=source, index=0, code='print("hello", flush=True)\n')

    payload = build_execution_payload(block, build_context)

    assert payload.script_path == build_context.payload_path(0)
    assert payload.result_path == build_context.result_path(0)
    assert payload.log_path == build_context.log_path(0)
    assert payload.execution_cwd == source.parent
    assert payload.script_path.read_text(encoding="utf-8") == payload.script_text
    assert "import pandas as pd" in payload.script_text
    assert 'print("hello", flush=True)' in payload.script_text


def test_build_execution_payloads_skips_markdown_and_preserves_document_order(
    tmp_path: Path,
) -> None:
    source = _source_file(tmp_path)
    build_context = BuildContext.create(source, keep=True)
    first_block = _block(source_path=source, index=0, code='print("first")\n')
    second_block = _block(source_path=source, index=1, code='print("second")\n')
    document = DocumentModel(
        source_path=source,
        nodes=[
            MarkdownNode(
                node_id="node-0001",
                text="Intro\n",
                location=_location(source, 1),
            ),
            first_block,
            MarkdownNode(
                node_id="node-0002",
                text="Bridge\n",
                location=_location(source, 2),
            ),
            second_block,
        ],
    )

    payloads = build_execution_payloads(document, build_context)

    assert [payload.block.node_id for payload in payloads] == [
        first_block.node_id,
        second_block.node_id,
    ]
    assert [payload.script_path.name for payload in payloads] == [
        "payload_000.py",
        "payload_001.py",
    ]


def test_run_payload_captures_stdout_and_timing(tmp_path: Path) -> None:
    source = _source_file(tmp_path)
    build_context = BuildContext.create(source, keep=True)
    payload = build_execution_payload(
        _block(
            source_path=source,
            index=0,
            code='print("hello from block", flush=True)\nvalue = 42\n',
        ),
        build_context,
    )

    result = run_payload(payload, timeout_seconds=5.0)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.streams.stdout == "hello from block\n"
    assert result.streams.stderr == ""
    assert result.timing.timeout_seconds == 5.0
    assert result.timing.duration_ms is not None
    assert result.timing.duration_ms >= 0
    assert payload.log_path.read_text(encoding="utf-8").count("hello from block") == 1


def test_run_payloads_executes_in_document_order(tmp_path: Path) -> None:
    source = _source_file(tmp_path)
    build_context = BuildContext.create(source, keep=True)
    document = DocumentModel(
        source_path=source,
        nodes=[
            _block(source_path=source, index=0, code='print("first", flush=True)\n'),
            _block(source_path=source, index=1, code='print("second", flush=True)\n'),
        ],
    )

    results = run_payloads(
        build_execution_payloads(document, build_context),
        timeout_seconds=5.0,
    )

    assert [result.block.block_index for result in results] == [0, 1]
    assert [result.streams.stdout for result in results] == ["first\n", "second\n"]


def test_run_payloads_does_not_share_state_between_blocks(tmp_path: Path) -> None:
    source = _source_file(tmp_path)
    build_context = BuildContext.create(source, keep=True)
    document = DocumentModel(
        source_path=source,
        nodes=[
            _block(
                source_path=source,
                index=0,
                code='x = 41\nprint("ready", flush=True)\n',
            ),
            _block(
                source_path=source,
                index=1,
                code="print(x, flush=True)\n",
            ),
        ],
    )

    payloads = build_execution_payloads(document, build_context)

    with pytest.raises(ExecutionError) as exc_info:
        run_payloads(payloads, timeout_seconds=5.0)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.block_id == "block-0002"
    assert diagnostic.block_index == 1
    assert diagnostic.source_path == source
    assert "NameError" in (diagnostic.stderr or "")
    assert "ready" in payloads[0].log_path.read_text(encoding="utf-8")


def test_run_payload_raises_execution_error_with_diagnostics(tmp_path: Path) -> None:
    source = _source_file(tmp_path)
    build_context = BuildContext.create(source, keep=True)
    payload = build_execution_payload(
        _block(
            source_path=source,
            index=0,
            code='print("before crash", flush=True)\nraise RuntimeError("boom")\n',
        ),
        build_context,
    )

    with pytest.raises(ExecutionError) as exc_info:
        run_payload(payload, timeout_seconds=5.0)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.block_id == "block-0001"
    assert diagnostic.block_type is BlockType.TABLE
    assert diagnostic.location == payload.block.location
    assert diagnostic.stdout == "before crash\n"
    assert "RuntimeError: boom" in (diagnostic.stderr or "")
    assert diagnostic.duration_ms is not None


def test_run_payload_raises_timeout_error_with_diagnostics(tmp_path: Path) -> None:
    source = _source_file(tmp_path)
    build_context = BuildContext.create(source, keep=True)
    payload = build_execution_payload(
        _block(
            source_path=source,
            index=0,
            code='print("start", flush=True)\nwhile True:\n    pass\n',
        ),
        build_context,
    )

    with pytest.raises(TimeoutError) as exc_info:
        run_payload(payload, timeout_seconds=0.1)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.block_id == "block-0001"
    assert diagnostic.stdout in {"", "start\n"}
    assert diagnostic.duration_ms is not None
    assert diagnostic.duration_ms >= 0
    assert "execution exceeded 0.1 seconds" == diagnostic.exception_message
