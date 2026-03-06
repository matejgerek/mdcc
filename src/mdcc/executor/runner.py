from __future__ import annotations

import subprocess
import sys
import time

from mdcc.errors import ErrorContext, ExecutionError, TimeoutError
from mdcc.executor.result import extract_raw_value
from mdcc.models import (
    BlockExecutionResult,
    ExecutionPayload,
    ExecutionStatus,
    ExecutionStreams,
    ExecutionTiming,
)


def run_payload(
    payload: ExecutionPayload,
    timeout_seconds: float,
) -> BlockExecutionResult:
    """Execute one payload in a fresh Python subprocess."""
    started_at = time.perf_counter()
    try:
        completed = subprocess.run(
            [sys.executable, str(payload.script_path)],
            capture_output=True,
            text=True,
            cwd=payload.execution_cwd,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = _duration_ms(started_at)
        stdout = _normalize_output(exc.stdout)
        stderr = _normalize_output(exc.stderr)
        _write_log(
            payload=payload,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            timeout_seconds=timeout_seconds,
            exit_code=None,
            timed_out=True,
        )
        raise TimeoutError.from_message(
            "block execution timed out",
            context=_build_error_context(payload),
            source_snippet=_source_snippet(payload),
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            exception_message=f"execution exceeded {timeout_seconds} seconds",
        ) from exc

    duration_ms = _duration_ms(started_at)
    _write_log(
        payload=payload,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_ms=duration_ms,
        timeout_seconds=timeout_seconds,
        exit_code=completed.returncode,
        timed_out=False,
    )

    if completed.returncode != 0:
        raise ExecutionError.from_message(
            "block execution failed",
            context=_build_error_context(payload),
            source_snippet=_source_snippet(payload),
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_ms=duration_ms,
            exception_message=f"subprocess exited with status {completed.returncode}",
        )

    # ── T10: extract final expression result ──
    raw_value, raw_type_name = extract_raw_value(payload.result_path)

    return BlockExecutionResult(
        block=payload.block,
        status=ExecutionStatus.SUCCESS,
        streams=ExecutionStreams(stdout=completed.stdout, stderr=completed.stderr),
        timing=ExecutionTiming(
            duration_ms=duration_ms,
            timeout_seconds=timeout_seconds,
        ),
        raw_value=raw_value,
        raw_type_name=raw_type_name,
    )


def run_payloads(
    payloads: list[ExecutionPayload],
    timeout_seconds: float,
) -> list[BlockExecutionResult]:
    """Execute payloads in deterministic order and stop on first failure."""
    return [run_payload(payload, timeout_seconds) for payload in payloads]


def _build_error_context(payload: ExecutionPayload) -> ErrorContext:
    location = payload.block.location
    return ErrorContext(
        source_path=location.source_path if location is not None else None,
        block_id=payload.block.node_id,
        block_type=payload.block.block_type,
        block_index=payload.block.block_index,
        location=location,
    )


def _source_snippet(payload: ExecutionPayload) -> str | None:
    location = payload.block.location
    if location is None:
        return None
    return location.snippet


def _duration_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000


def _normalize_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode()
    return value


def _write_log(
    *,
    payload: ExecutionPayload,
    stdout: str,
    stderr: str,
    duration_ms: float,
    timeout_seconds: float,
    exit_code: int | None,
    timed_out: bool,
) -> None:
    lines = [
        f"block_id: {payload.block.node_id}",
        f"block_index: {payload.block.block_index}",
        f"block_type: {payload.block.block_type.value}",
        f"script_path: {payload.script_path}",
        f"result_path: {payload.result_path}",
        f"cwd: {payload.execution_cwd}",
        f"timeout_seconds: {timeout_seconds}",
        f"duration_ms: {duration_ms:.3f}",
        f"timed_out: {str(timed_out).lower()}",
        f"exit_code: {exit_code if exit_code is not None else 'timeout'}",
        "",
        "stdout:",
        stdout.rstrip("\n"),
        "",
        "stderr:",
        stderr.rstrip("\n"),
    ]
    payload.log_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


__all__ = ["run_payload", "run_payloads"]
