from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, TypeAlias, cast

import mistune

from mdcc.models import BlockType, ExecutableBlockNode

ReferenceRegistry: TypeAlias = dict[str, "ResolvedReference"]
REFERENCE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9:_-])@(?P<label>[A-Za-z][A-Za-z0-9:_-]*)"
)
_MARKDOWN_AST_RENDERER = mistune.create_markdown(renderer="ast")


@dataclass(frozen=True, slots=True)
class ResolvedReference:
    label: str
    block_id: str
    block_type: BlockType
    ordinal: int

    @property
    def display_name(self) -> str:
        if self.block_type is BlockType.CHART:
            return "Figure"
        if self.block_type is BlockType.TABLE:
            return "Table"

        msg = f"unsupported block type for cross-reference: {self.block_type}"
        raise ValueError(msg)

    @property
    def text(self) -> str:
        return f"{self.display_name} {self.ordinal}"


def build_reference_registry(
    blocks: list[ExecutableBlockNode],
) -> tuple[ReferenceRegistry, list[tuple[str, ExecutableBlockNode]]]:
    registry: ReferenceRegistry = {}
    duplicates: list[tuple[str, ExecutableBlockNode]] = []
    counters = {
        BlockType.CHART: 0,
        BlockType.TABLE: 0,
    }

    for block in blocks:
        label = block.metadata.label
        if label is None:
            continue

        if label in registry:
            duplicates.append((label, block))
            continue

        counters[block.block_type] += 1
        registry[label] = ResolvedReference(
            label=label,
            block_id=block.node_id,
            block_type=block.block_type,
            ordinal=counters[block.block_type],
        )

    return registry, duplicates


def iter_reference_labels(text: str) -> list[str]:
    return [match.group("label") for match in REFERENCE_PATTERN.finditer(text)]


def iter_reference_labels_in_markdown(text: str) -> list[str]:
    tokens_result, _ = _MARKDOWN_AST_RENDERER.parse(text)
    tokens = cast(list[dict[str, Any]], tokens_result)
    labels: list[str] = []
    _collect_reference_labels_from_tokens(tokens, labels)
    return labels


def _collect_reference_labels_from_tokens(
    tokens: list[dict[str, Any]],
    labels: list[str],
) -> None:
    for token in tokens:
        token_type = token.get("type")
        if token_type == "text":
            raw = token.get("raw")
            if isinstance(raw, str):
                labels.extend(iter_reference_labels(raw))

        children = token.get("children")
        if isinstance(children, list):
            _collect_reference_labels_from_tokens(children, labels)


__all__ = [
    "REFERENCE_PATTERN",
    "ReferenceRegistry",
    "ResolvedReference",
    "build_reference_registry",
    "iter_reference_labels",
    "iter_reference_labels_in_markdown",
]
