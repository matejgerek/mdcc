"""Fixed runtime prelude and result-capture epilogue.

Every execution payload is assembled as::

    <prelude>     — imports, MDCC_RESULT_PATH constant
    <user code>   — the block's source code (possibly rewritten)
    <epilogue>    — serialises the last-expression value to MDCC_RESULT_PATH

The prelude makes ``pd``, ``np``, and ``alt`` available without user
imports.  The epilogue is injected *only* when the payload builder
detects that the block's last statement is an expression — see
:func:`payload._rewrite_last_expression`.
"""

from __future__ import annotations

import json
from pathlib import Path

_PRELUDE_TEMPLATE = """\
import atexit
import builtins as _mdcc_builtins
import json as _mdcc_json
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd

MDCC_RESULT_PATH = Path({result_path})
MDCC_RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
MDCC_DEPENDENCY_PATH = Path({dependency_path})
MDCC_DEPENDENCY_PATH.parent.mkdir(parents=True, exist_ok=True)
_MDCC_DEPENDENCIES = set()
MDCC_DATASET_MANIFEST_PATH = Path({dataset_manifest_path})
MDCC_DATASET_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
MDCC_DATASET_PAYLOADS_DIR = Path({dataset_payloads_dir})
MDCC_DATASET_PAYLOADS_DIR.mkdir(parents=True, exist_ok=True)
MDCC_CAPTURE_DATASETS = {capture_datasets}
_MDCC_DATASET_CAPTURES = []

def _mdcc_normalize_dependency(_path):
    if isinstance(_path, int):
        return None
    if not isinstance(_path, (str, bytes, Path)):
        return None
    try:
        return str(Path(_path).expanduser().resolve())
    except Exception:
        return None

def _mdcc_record_dependency(_path):
    _normalized = _mdcc_normalize_dependency(_path)
    if _normalized is not None:
        _MDCC_DEPENDENCIES.add(_normalized)

def _mdcc_flush_dependencies():
    MDCC_DEPENDENCY_PATH.write_text(
        _mdcc_json.dumps(sorted(_MDCC_DEPENDENCIES)),
        encoding="utf-8",
    )
    MDCC_DATASET_MANIFEST_PATH.write_text(
        _mdcc_json.dumps(_MDCC_DATASET_CAPTURES),
        encoding="utf-8",
    )

atexit.register(_mdcc_flush_dependencies)

_mdcc_open = _mdcc_builtins.open

def _mdcc_is_read_mode(_mode):
    return not any(_flag in _mode for _flag in "wax+")

def _mdcc_open_wrapper(_file, _mode="r", *args, **kwargs):
    _handle = _mdcc_open(_file, _mode, *args, **kwargs)
    if _mdcc_is_read_mode(_mode):
        _mdcc_record_dependency(_file)
    return _handle

def _mdcc_wrap_pandas_reader(_reader):
    def _wrapped(_path, *args, **kwargs):
        _result = _reader(_path, *args, **kwargs)
        _mdcc_record_dependency(_path)
        if MDCC_CAPTURE_DATASETS and isinstance(_result, pd.DataFrame):
            _capture_index = len(_MDCC_DATASET_CAPTURES)
            _payload_path = (
                MDCC_DATASET_PAYLOADS_DIR
                / f"dataset_{{_capture_index:03d}}.parquet"
            )
            _result.to_parquet(_payload_path, index=False)
            _MDCC_DATASET_CAPTURES.append(
                {{
                    "ordinal": _capture_index,
                    "source_kind": _reader.__name__,
                    "source_path": _mdcc_normalize_dependency(_path),
                    "payload_path": str(_payload_path),
                }}
            )
        return _result
    return _wrapped

_mdcc_builtins.open = _mdcc_open_wrapper
pd.read_csv = _mdcc_wrap_pandas_reader(pd.read_csv)
pd.read_json = _mdcc_wrap_pandas_reader(pd.read_json)
pd.read_excel = _mdcc_wrap_pandas_reader(pd.read_excel)
pd.read_parquet = _mdcc_wrap_pandas_reader(pd.read_parquet)
"""

_EPILOGUE_TEMPLATE = """\
# ── mdcc result capture ──────────────────────────────────────────────
import pickle as _mdcc_pickle

def _mdcc_save_result(_val):
    _envelope = {{
        "has_value": True,
        "type_name": type(_val).__name__,
        "type_module": type(_val).__module__,
        "value": _val,
    }}
    try:
        MDCC_RESULT_PATH.write_bytes(_mdcc_pickle.dumps(_envelope))
    except Exception as _mdcc_exc:
        # Value evaluated successfully but is not picklable.
        # Record type metadata so downstream validation can
        # classify the failure properly instead of raising an
        # execution error here.
        _fallback = {{
            "has_value": True,
            "type_name": type(_val).__name__,
            "type_module": type(_val).__module__,
            "value": None,
            "pickle_error": str(_mdcc_exc),
        }}
        MDCC_RESULT_PATH.write_bytes(_mdcc_pickle.dumps(_fallback))
    return _val

{result_variable} = _mdcc_save_result({expression})
"""

_NO_EXPR_EPILOGUE = """\
# ── mdcc result capture (no final expression) ────────────────────────
import pickle as _mdcc_pickle

_mdcc_envelope = {"has_value": False, "type_name": None, "type_module": None}
MDCC_RESULT_PATH.write_bytes(_mdcc_pickle.dumps(_mdcc_envelope))
"""


def build_runtime_prelude(
    result_path: Path,
    dependency_path: Path,
    dataset_manifest_path: Path,
    dataset_payloads_dir: Path,
    *,
    capture_datasets: bool,
) -> str:
    """Return the deterministic runtime prelude for an execution payload."""
    return _PRELUDE_TEMPLATE.format(
        result_path=json.dumps(str(result_path)),
        dependency_path=json.dumps(str(dependency_path)),
        dataset_manifest_path=json.dumps(str(dataset_manifest_path)),
        dataset_payloads_dir=json.dumps(str(dataset_payloads_dir)),
        capture_datasets=repr(capture_datasets),
    )


def build_capture_mode(has_expression_result: bool) -> str:
    """Return the canonical capture mode identifier for cache fingerprinting."""
    return "final_expression" if has_expression_result else "no_final_expression"


def runtime_prelude_template() -> str:
    """Return the prelude template used for cache fingerprinting."""
    return _PRELUDE_TEMPLATE


def build_result_epilogue(
    expression: str,
    *,
    result_variable: str = "_mdcc_result",
) -> str:
    """Return the epilogue that captures a final expression value.

    Parameters
    ----------
    expression:
        The Python source of the final expression.
    result_variable:
        Variable name used to hold the result (defaults to
        ``_mdcc_result``).
    """
    return _EPILOGUE_TEMPLATE.format(
        expression=expression,
        result_variable=result_variable,
    )


def build_no_expression_epilogue() -> str:
    """Return the epilogue used when the block has no final expression."""
    return _NO_EXPR_EPILOGUE


__all__ = [
    "build_capture_mode",
    "build_no_expression_epilogue",
    "build_result_epilogue",
    "build_runtime_prelude",
    "runtime_prelude_template",
]
