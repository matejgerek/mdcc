from __future__ import annotations

import json
from pathlib import Path

_PRELUDE_TEMPLATE = """from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd

# Reserved for T10 result extraction.
MDCC_RESULT_PATH = Path({result_path})
MDCC_RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
"""


def build_runtime_prelude(result_path: Path) -> str:
    """Return the deterministic runtime prelude for an execution payload."""
    return _PRELUDE_TEMPLATE.format(result_path=json.dumps(str(result_path)))


__all__ = ["build_runtime_prelude"]
