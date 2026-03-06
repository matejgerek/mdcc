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
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd

# Reserved for result extraction (T10).
MDCC_RESULT_PATH = Path({result_path})
MDCC_RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
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
        # Record type metadata so downstream validation (T11) can
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


def build_runtime_prelude(result_path: Path) -> str:
    """Return the deterministic runtime prelude for an execution payload."""
    return _PRELUDE_TEMPLATE.format(result_path=json.dumps(str(result_path)))


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
    "build_no_expression_epilogue",
    "build_result_epilogue",
    "build_runtime_prelude",
]
