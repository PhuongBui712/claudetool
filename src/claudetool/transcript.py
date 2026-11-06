"""Parse a Claude Code transcript file into display blocks.

Claude Code writes one JSONL entry per assistant content block and sends tool
results back as `user` entries, so the parser re-pairs them into the blocks a
reader cares about. Vocabulary follows `GLOSSARY.md`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from pathlib import Path

__all__ = ["Block", "Kind", "parse_entries", "parse_transcript"]

_INTERRUPTED_PREFIX = "[Request interrupted by user"
_INJECTED_PREFIXES = (
    "<task-notification>",
    "<system-reminder>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<local-command-caveat>",
    "<bash-stdout>",
    "<bash-stderr>",
    "Another Claude session sent a message",
)
_COMMAND_NAME_RE = re.compile(r"<command-name>(.*?)</command-name>", re.DOTALL)
_COMMAND_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)
_BASH_INPUT_RE = re.compile(r"<bash-input>(.*?)</bash-input>", re.DOTALL)
_AGENT_ID_RE = re.compile(r"agentId: (\w+)")
# The tool input key that best names what a call did, in priority order.
_SUMMARY_KEYS = (
    "command",
    "file_path",
    "pattern",
    "description",
    "url",
    "query",
    "skill",
    "path",
    "prompt",
)
_CONVERSATION_MARKERS = (b'"type":"user"', b'"type":"assistant"', b'"type":"system"')
_PROGRESS_EVERY = 2000


class Kind(StrEnum):
    """What a block shows."""

    USER = "user"
    AGENT = "agent"
    RESULT = "result"
    TOOL = "tool"
    THINKING = "thinking"
    META = "meta"
    INTERRUPTED = "interrupted"
    COMPACTED = "compacted"


@dataclass(slots=True)
class Block:
    """One rendered unit of a transcript.

    Attributes:
        kind: What the block shows.
        text: The body; for a tool call, its input as indented JSON.
        uuid: The transcript entry the block starts at.
        timestamp: When that entry was written.
        tool_name: Tool calls only: the tool's name.
        summary: Tool calls: the key argument on one line. Meta: its subtype.
        output: Tool calls only: the result text, empty until it arrives.
        is_error: Tool calls only: whether the result was an error.
        agent_id: `Agent` calls only: the subagent the call launched.
    """

    kind: Kind
    text: str
    uuid: str = ""
    timestamp: datetime | None = None
    tool_name: str = ""
    summary: str = ""
    output: str = ""
    is_error: bool = False
    agent_id: str = ""


def parse_transcript(
    path: Path, *, on_progress: Callable[[float], None] | None = None
) -> list[Block]:
    """Read a transcript file into blocks, reporting the fraction read so far."""
    return parse_entries(_read_entries(path, on_progress))


def parse_entries(entries: Iterable[dict[str, Any]]) -> list[Block]:
    """Turn decoded transcript entries into blocks, marking each turn's result."""
    blocks: list[Block] = []
    tools: dict[str, Block] = {}
    for entry in entries:
        etype = entry.get("type")
        if etype == "assistant":
            _add_assistant(entry, blocks, tools)
        elif etype == "user":
            _add_user(entry, blocks, tools)
        elif etype == "system":
            _add_system(entry, blocks)
    _mark_results(blocks)
    return blocks


def _read_entries(
    path: Path, on_progress: Callable[[float], None] | None
) -> Iterator[dict[str, Any]]:
    total = path.stat().st_size or 1
    done = 0
    with path.open("rb") as fh:
        for i, raw in enumerate(fh):
            done += len(raw)
            if on_progress and i % _PROGRESS_EVERY == 0:
                on_progress(done / total)
            # Cheap byte test first: most lines are harness bookkeeping.
            if not any(marker in raw for marker in _CONVERSATION_MARKERS):
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                yield entry
    if on_progress:
        on_progress(1.0)


def _add_assistant(
    entry: dict[str, Any], blocks: list[Block], tools: dict[str, Block]
) -> None:
    uuid, when = _origin(entry)
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    for item in content if isinstance(content, list) else []:
        itype = item.get("type") if isinstance(item, dict) else None
        if itype == "text" and item.get("text", "").strip():
            blocks.append(Block(Kind.AGENT, item["text"].strip(), uuid, when))
        elif itype == "thinking" and item.get("thinking", "").strip():
            blocks.append(Block(Kind.THINKING, item["thinking"].strip(), uuid, when))
        elif itype == "tool_use":
            tool_input = item.get("input") or {}
            block = Block(
                Kind.TOOL,
                json.dumps(tool_input, indent=2, ensure_ascii=False),
                uuid,
                when,
                tool_name=item.get("name", ""),
                summary=_tool_summary(tool_input),
            )
            tools[item.get("id", "")] = block
            blocks.append(block)


def _add_user(
    entry: dict[str, Any], blocks: list[Block], tools: dict[str, Block]
) -> None:
    content = (entry.get("message") or {}).get("content")
    results = [
        item
        for item in (content if isinstance(content, list) else [])
        if isinstance(item, dict) and item.get("type") == "tool_result"
    ]
    if results:
        _attach_results(entry, results, tools)
        return
    text = _content_text(content).strip()
    if not text:
        return
    uuid, when = _origin(entry)
    if entry.get("isCompactSummary"):
        _add_compacted(blocks, text, uuid, when)
    elif text.startswith(_INTERRUPTED_PREFIX):
        blocks.append(Block(Kind.INTERRUPTED, text, uuid, when))
    elif entry.get("isMeta") or text.startswith(_INJECTED_PREFIXES):
        blocks.append(Block(Kind.META, text, uuid, when))
    else:
        blocks.append(Block(Kind.USER, _typed_text(text), uuid, when))


def _add_system(entry: dict[str, Any], blocks: list[Block]) -> None:
    content = entry.get("content")
    if not isinstance(content, str) or not content.strip():
        return
    uuid, when = _origin(entry)
    subtype = entry.get("subtype", "")
    if subtype == "compact_boundary":
        blocks.append(Block(Kind.COMPACTED, content.strip(), uuid, when))
    elif subtype == "local_command" and "<command-name>" in content:
        # A slash command run locally (e.g. /cd): typed by the human, never sent.
        blocks.append(Block(Kind.USER, _typed_text(content), uuid, when))
    else:
        blocks.append(Block(Kind.META, content.strip(), uuid, when, summary=subtype))


def _attach_results(
    entry: dict[str, Any], results: list[dict[str, Any]], tools: dict[str, Block]
) -> None:
    launched = entry.get("toolUseResult")
    for item in results:
        block = tools.get(item.get("tool_use_id", ""))
        if block is None:
            continue
        block.output = _content_text(item.get("content")).strip()
        block.is_error = bool(item.get("is_error"))
        if isinstance(launched, dict) and launched.get("agentId"):
            block.agent_id = str(launched["agentId"])
        elif block.tool_name in ("Agent", "Task"):
            found = _AGENT_ID_RE.search(block.output)
            block.agent_id = found.group(1) if found else ""


def _add_compacted(
    blocks: list[Block], text: str, uuid: str, when: datetime | None
) -> None:
    # The boundary marker and the summary arrive as two entries; show them as one.
    if blocks and blocks[-1].kind is Kind.COMPACTED:
        blocks[-1].text = text
    else:
        blocks.append(Block(Kind.COMPACTED, text, uuid, when))


def _mark_results(blocks: list[Block]) -> None:
    turn_end: int | None = None
    for i, block in enumerate(blocks):
        if block.kind is Kind.USER:
            _promote(blocks, turn_end)
            turn_end = None
        elif block.kind not in (Kind.THINKING, Kind.META):
            turn_end = i
    _promote(blocks, turn_end)


def _promote(blocks: list[Block], index: int | None) -> None:
    if index is not None and blocks[index].kind is Kind.AGENT:
        blocks[index].kind = Kind.RESULT


def _typed_text(text: str) -> str:
    """Render slash commands and `!` shell input the way the human typed them."""
    name = _COMMAND_NAME_RE.search(text)
    if name:
        args = _COMMAND_ARGS_RE.search(text)
        tail = args.group(1).strip() if args else ""
        return f"{name.group(1).strip()} {tail}".strip()
    bash = _BASH_INPUT_RE.search(text)
    if bash:
        return f"! {bash.group(1).strip()}"
    return text


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            parts.append(str(item.get("text", "")))
        elif item.get("type") == "image":
            parts.append("[image]")
    return "\n".join(parts)


def _tool_summary(tool_input: object) -> str:
    if not isinstance(tool_input, dict):
        return ""
    for key in _SUMMARY_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().splitlines()[0]
    return ""


def _origin(entry: dict[str, Any]) -> tuple[str, datetime | None]:
    stamp = entry.get("timestamp")
    when = None
    if isinstance(stamp, str):
        try:
            when = datetime.fromisoformat(stamp)
        except ValueError:
            when = None
    return str(entry.get("uuid", "")), when
