"""Search command: find text in the visible conversation of a project's sessions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from claudetool.rendering import BOLD, CYAN, DIM, GREEN, RED, RESET, YELLOW
from claudetool.transcript import Kind, parse_entries

if TYPE_CHECKING:
    from argparse import Namespace
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from claudetool.sessions import Session

__all__ = ["SearchHit", "cmd_search", "search_sessions"]

_CHECK_EVERY = 2000
_CONTEXT = 60


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One match, addressed by the viewer block it lives in."""

    session_file: Path
    uuid: str
    kind: Kind
    timestamp: datetime | None
    snippet: str


def _timestamp(entry: dict[str, Any]) -> datetime | None:
    stamp = entry.get("timestamp")
    if not isinstance(stamp, str):
        return None
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:
        return None


def _is_before(when: datetime, since: datetime) -> bool:
    # Transcript stamps are UTC; `since` is a naive local date.
    if when.tzinfo and since.tzinfo is None:
        when = when.astimezone().replace(tzinfo=None)
    return when < since


def _result_text(entry: dict[str, Any]) -> str | None:
    """Return the text of a tool_result entry, or None if it is not one."""
    content = (entry.get("message") or {}).get("content")
    if not isinstance(content, list):
        return None
    results = [
        i for i in content if isinstance(i, dict) and i.get("type") == "tool_result"
    ]
    if not results:
        return None
    parts: list[str] = []
    for item in results:
        body = item.get("content")
        if isinstance(body, str):
            parts.append(body)
        elif isinstance(body, list):
            parts += [
                str(b.get("text", ""))
                for b in body
                if isinstance(b, dict) and b.get("type") == "text"
            ]
    return "\n".join(parts)


def _snippet(text: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - _CONTEXT)
    end = min(len(text), match.end() + _CONTEXT)
    body = " ".join(text[start:end].split())
    return f"{'...' if start else ''}{body}{'...' if end < len(text) else ''}"


def _find_hit(
    entry: dict[str, Any], pattern: re.Pattern[str], file: Path
) -> SearchHit | None:
    """Match the human-visible text of `entry`, ignoring harness bookkeeping."""
    when = _timestamp(entry)
    result = _result_text(entry)
    if result is not None:
        found = pattern.search(result)
        if not found:
            return None
        uuid = entry.get("sourceToolAssistantUUID") or entry.get("uuid", "")
        return SearchHit(file, str(uuid), Kind.TOOL, when, _snippet(result, found))
    for block in parse_entries([entry]):
        found = pattern.search(block.text)
        if found:
            return SearchHit(
                file, block.uuid, block.kind, when, _snippet(block.text, found)
            )
    return None


def search_sessions(
    files: list[Path],
    query: str,
    *,
    since: datetime | None = None,
    max_results: int = 50,
    cancelled: Callable[[], bool] = lambda: False,
) -> Iterator[SearchHit]:
    """Yield matches of `query` (case-insensitive) in the files' conversations.

    Lines are prefiltered on their raw text, so a query containing characters
    JSON escapes (quotes, newlines, non-ASCII) can miss matches.
    """
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    found = 0
    for file in files:
        if found >= max_results or cancelled():
            return
        for hit in _scan_file(file, pattern, cancelled):
            if since and hit.timestamp and _is_before(hit.timestamp, since):
                continue
            yield hit
            found += 1
            if found >= max_results:
                return


def _scan_file(
    file: Path, pattern: re.Pattern[str], cancelled: Callable[[], bool]
) -> Iterator[SearchHit]:
    try:
        with file.open("rb") as fh:
            for i, raw in enumerate(fh):
                if i % _CHECK_EVERY == _CHECK_EVERY - 1 and cancelled():
                    return
                if not pattern.search(raw.decode("utf-8", "replace")):
                    continue
                try:
                    entry = json.loads(raw)
                except ValueError:
                    continue
                hit = (
                    _find_hit(entry, pattern, file) if isinstance(entry, dict) else None
                )
                if hit:
                    yield hit
    except OSError:
        return


def _highlight(text: str, pattern: re.Pattern[str]) -> str:
    return pattern.sub(lambda m: f"{RED}{BOLD}{m.group()}{RESET}", text)


def cmd_search(sessions: list[Session], args: Namespace) -> None:
    """Search the current project's top-level sessions and print grouped hits."""
    query = args.query
    since = None
    if args.since:
        try:
            since = datetime.fromisoformat(args.since)
        except ValueError:
            print(
                f"{RED}Invalid date format:{RESET} {args.since}  (expected YYYY-MM-DD)"
            )
            return

    by_file = {s["file"]: s for s in sessions}
    results = list(
        search_sessions(list(by_file), query, since=since, max_results=args.limit)
    )
    if not results:
        print(f'\n  {DIM}No matches for{RESET} {BOLD}"{query}"{RESET}')
        if since:
            print(f"  {DIM}(filtered to sessions since {args.since}){RESET}")
        return

    pattern = re.compile(re.escape(query), re.IGNORECASE)
    print(f'\n  {GREEN}{len(results)}{RESET} match(es) for {BOLD}"{query}"{RESET}')
    if since:
        print(f"  {DIM}(since {args.since}){RESET}")
    print()

    prev = None
    for hit in results:
        if hit.session_file != prev:
            s = by_file[hit.session_file]
            sid = s["session_id"]
            label = s["label"] or sid[:16]
            date_str = s["last_active"].strftime("%Y-%m-%d %H:%M")
            print(
                f"  {CYAN}{sid[:16]}{RESET}  {GREEN}{label[:50]}{RESET}"
                f"  {DIM}{date_str}{RESET}"
            )
            prev = hit.session_file
        when = hit.timestamp.strftime("%H:%M:%S") if hit.timestamp else "       "
        who = (
            f"{CYAN}you{RESET}"
            if hit.kind is Kind.USER
            else f"{YELLOW}{hit.kind.value}{RESET}"
        )
        print(f"    {DIM}{when}{RESET}  {who}  {_highlight(hit.snippet, pattern)}")

    print(f"\n  {DIM}Preview a session:{RESET}  claudetool preview <session-id>")
