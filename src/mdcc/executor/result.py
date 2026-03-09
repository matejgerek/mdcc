"""Final expression result extraction.

Reads the pickled result envelope written by the execution payload and
converts it into the ``raw_value`` / ``raw_type_name`` pair stored on
:class:`~mdcc.models.BlockExecutionResult`.

The serialisation format is a simple dict persisted via :mod:`pickle`:

.. code-block:: python

    {
        "has_value": True,
        "type_name": "DataFrame",
        "type_module": "pandas.core.frame",
        "value": <the actual Python object>,
    }

If the block's last statement was *not* an expression (e.g. an assignment
or a ``for`` loop), the envelope carries ``has_value = False`` and no
``value`` key.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import json

from mdcc.models import RuntimeDatasetCapture


def read_result_envelope(result_path: Path) -> dict[str, Any] | None:
    """Deserialize a result envelope produced by a payload script.

    Returns ``None`` if the result file does not exist (the block
    may not have produced a final expression).
    """
    if not result_path.exists():
        return None

    data = pickle.loads(result_path.read_bytes())  # noqa: S301 – trusted data from our own subprocess
    if not isinstance(data, dict):
        return None
    return data


def extract_raw_value(result_path: Path) -> tuple[Any, str | None]:
    """Return ``(raw_value, raw_type_name)`` from a result envelope.

    * If the file is missing or contains ``has_value = False``,
      returns ``(None, None)``.
    * Otherwise returns the deserialised value and its qualified type
      name string.
    """
    envelope = read_result_envelope(result_path)
    if envelope is None or not envelope.get("has_value", False):
        return None, None

    value = envelope.get("value")
    type_module: str = envelope.get("type_module", "")
    type_name: str = envelope.get("type_name", type(value).__name__)

    qualified = f"{type_module}.{type_name}" if type_module else type_name
    return value, qualified


def read_runtime_dataset_captures(
    dataset_manifest_path: Path,
) -> list[RuntimeDatasetCapture]:
    """Deserialize runtime dataset capture facts produced by the prelude."""
    if not dataset_manifest_path.exists():
        return []

    try:
        payload = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(payload, list):
        return []

    captures: list[RuntimeDatasetCapture] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            captures.append(RuntimeDatasetCapture.model_validate(item))
        except Exception:
            continue
    return captures


__all__ = [
    "extract_raw_value",
    "read_result_envelope",
    "read_runtime_dataset_captures",
]
