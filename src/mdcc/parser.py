from __future__ import annotations

import re
from dataclasses import dataclass

from mdcc.errors import ErrorContext, ParseError
from mdcc.models import (
    BlockType,
    DocumentModel,
    ExecutableBlockNode,
    MarkdownNode,
    SourceDocumentInput,
    SourceLocation,
    SourcePosition,
    SourceSpan,
)

FENCE_RE = re.compile(
    r"^(?P<indent>[ \t]{0,3})(?P<fence>`{3,}|~{3,})(?P<info>[^\r\n]*)$"
)
CLOSE_FENCE_RE = re.compile(r"^(?P<indent>[ \t]{0,3})(?P<fence>`{3,}|~{3,})[ \t]*$")
SUPPORTED_BLOCK_TYPES = {block_type.value: block_type for block_type in BlockType}
ATTRIBUTE_RE = re.compile(r'(?P<key>[A-Za-z][A-Za-z0-9_-]*)="(?P<value>[^"\r\n]*)"')


@dataclass
class FenceState:
    fence: str
    open_line: int
    open_line_text: str
    info_string: str
    block_type: BlockType | None = None
    raw_metadata: tuple[tuple[str, str], ...] = ()


def parse_document(source: SourceDocumentInput) -> DocumentModel:
    nodes: list[MarkdownNode | ExecutableBlockNode] = []
    lines = source.body_text.splitlines(keepends=True)
    markdown_buffer: list[str] = []
    markdown_start_line: int | None = None
    markdown_end_line: int | None = None
    executable_state: FenceState | None = None
    executable_lines: list[str] = []
    markdown_fence_state: FenceState | None = None
    markdown_node_index = 0
    executable_block_index = 0

    def append_markdown_line(line: str, line_number: int) -> None:
        nonlocal markdown_start_line, markdown_end_line
        if markdown_start_line is None:
            markdown_start_line = line_number
        markdown_end_line = line_number
        markdown_buffer.append(line)

    def flush_markdown() -> None:
        nonlocal markdown_node_index, markdown_start_line, markdown_end_line
        if (
            not markdown_buffer
            or markdown_start_line is None
            or markdown_end_line is None
        ):
            markdown_buffer.clear()
            markdown_start_line = None
            markdown_end_line = None
            return

        markdown_text = "".join(markdown_buffer)
        if markdown_text:
            markdown_node_index += 1
            nodes.append(
                MarkdownNode(
                    node_id=f"node-{markdown_node_index:04d}",
                    text=markdown_text,
                    location=_build_location(
                        source_path=source.source_path,
                        start_line=markdown_start_line,
                        end_line=markdown_end_line,
                        end_line_text=markdown_buffer[-1],
                        snippet=markdown_text,
                    ),
                )
            )

        markdown_buffer.clear()
        markdown_start_line = None
        markdown_end_line = None

    for line_number, line in enumerate(lines, start=1):
        if executable_state is not None:
            if _is_matching_close(line, executable_state.fence):
                executable_block_index += 1
                nodes.append(
                    ExecutableBlockNode(
                        node_id=f"block-{executable_block_index:04d}",
                        block_type=executable_state.block_type
                        or SUPPORTED_BLOCK_TYPES[executable_state.info_string],
                        code="".join(executable_lines),
                        block_index=executable_block_index - 1,
                        raw_metadata=executable_state.raw_metadata,
                        location=_build_location(
                            source_path=source.source_path,
                            start_line=executable_state.open_line,
                            end_line=line_number,
                            end_line_text=line,
                            snippet=executable_state.open_line_text,
                        ),
                    )
                )
                executable_state = None
                executable_lines = []
            else:
                executable_lines.append(line)
            continue

        if markdown_fence_state is not None:
            append_markdown_line(line, line_number)
            if _is_matching_close(line, markdown_fence_state.fence):
                markdown_fence_state = None
            continue

        opener = _parse_fence_opener(line, line_number)
        if opener is not None:
            if _looks_like_executable_fence(opener.info_string):
                opener = _parse_executable_fence_header(opener, source)

                flush_markdown()
                executable_state = opener
                executable_lines = []
                continue

            markdown_fence_state = opener
            append_markdown_line(line, line_number)
            continue

        append_markdown_line(line, line_number)

    if executable_state is not None:
        raise _build_parse_error(
            message=f"executable block fence is not closed: {executable_state.info_string}",
            source=source,
            line_number=executable_state.open_line,
            line_text=executable_state.open_line_text,
        )

    flush_markdown()

    return DocumentModel(
        source_path=source.source_path,
        frontmatter=source.frontmatter,
        nodes=nodes,
    )


def _parse_fence_opener(line: str, line_number: int) -> FenceState | None:
    match = FENCE_RE.match(line.rstrip("\r\n"))
    if match is None:
        return None

    return FenceState(
        fence=match.group("fence"),
        open_line=line_number,
        open_line_text=line,
        info_string=match.group("info").strip(),
    )


def _looks_like_executable_fence(info_string: str) -> bool:
    first_token = info_string.split(maxsplit=1)[0] if info_string else ""
    return first_token.startswith("mdcc_")


def _parse_executable_fence_header(
    opener: FenceState,
    source: SourceDocumentInput,
) -> FenceState:
    info_string = opener.info_string
    parts = info_string.split(maxsplit=1)
    block_name = parts[0] if parts else ""
    attribute_text = parts[1] if len(parts) == 2 else ""

    if block_name not in SUPPORTED_BLOCK_TYPES:
        raise _build_parse_error(
            message=f"unsupported or malformed executable block fence: {info_string}",
            source=source,
            line_number=opener.open_line,
            line_text=opener.open_line_text,
        )

    return FenceState(
        fence=opener.fence,
        open_line=opener.open_line,
        open_line_text=opener.open_line_text,
        info_string=block_name,
        block_type=SUPPORTED_BLOCK_TYPES[block_name],
        raw_metadata=_parse_metadata_attributes(
            attribute_text,
            source=source,
            line_number=opener.open_line,
            line_text=opener.open_line_text,
        ),
    )


def _parse_metadata_attributes(
    attribute_text: str,
    *,
    source: SourceDocumentInput,
    line_number: int,
    line_text: str,
) -> tuple[tuple[str, str], ...]:
    if not attribute_text.strip():
        return ()

    parsed: list[tuple[str, str]] = []
    position = 0
    length = len(attribute_text)

    while position < length:
        while position < length and attribute_text[position].isspace():
            position += 1

        if position >= length:
            break

        match = ATTRIBUTE_RE.match(attribute_text, position)
        if match is None:
            raise _build_parse_error(
                message="malformed executable block metadata attributes",
                source=source,
                line_number=line_number,
                line_text=line_text,
            )

        parsed.append((match.group("key"), match.group("value")))
        position = match.end()

        if position < length and not attribute_text[position].isspace():
            raise _build_parse_error(
                message="malformed executable block metadata attributes",
                source=source,
                line_number=line_number,
                line_text=line_text,
            )

    return tuple(parsed)


def _is_matching_close(line: str, opener_fence: str) -> bool:
    match = CLOSE_FENCE_RE.match(line.rstrip("\r\n"))
    if match is None:
        return False

    closing_fence = match.group("fence")
    return closing_fence[0] == opener_fence[0] and len(closing_fence) >= len(
        opener_fence
    )


def _build_location(
    source_path,
    start_line: int,
    end_line: int,
    end_line_text: str,
    snippet: str,
) -> SourceLocation:
    return SourceLocation(
        source_path=source_path,
        span=SourceSpan(
            start=SourcePosition(line=start_line, column=1),
            end=SourcePosition(line=end_line, column=_line_end_column(end_line_text)),
        ),
        snippet=_snippet(snippet),
    )


def _build_parse_error(
    message: str,
    source: SourceDocumentInput,
    line_number: int,
    line_text: str,
) -> ParseError:
    return ParseError.from_message(
        message,
        context=ErrorContext(
            source_path=source.source_path,
            location=_build_location(
                source_path=source.source_path,
                start_line=line_number,
                end_line=line_number,
                end_line_text=line_text,
                snippet=line_text,
            ),
        ),
        source_snippet=_snippet(line_text),
    )


def _line_end_column(line: str) -> int:
    stripped = line.rstrip("\r\n")
    return max(1, len(stripped))


def _snippet(text: str, limit: int = 160) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 3] + "..."


__all__ = ["parse_document"]
