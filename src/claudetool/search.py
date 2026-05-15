"""
Search command — full-text search across all sessions in a project.
"""

import json
import re
from datetime import datetime

from claudetool.rendering import BOLD, CYAN, DIM, GREEN, RED, YELLOW, RESET
from claudetool.sessions import (
    get_project_sessions_dir,
    _extract_text,
    parse_session_file,
)


def _parse_ts(ts) -> datetime | None:
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts / 1000)
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def _highlight(text: str, pattern: re.Pattern) -> str:
    """Wrap every match of *pattern* in RED+BOLD."""
    return pattern.sub(lambda m: f"{RED}{BOLD}{m.group()}{RESET}", text)


def search_sessions(
    cwd: str,
    query: str,
    since: datetime | None = None,
    max_results: int = 50,
) -> list[dict]:
    """Return a list of match dicts: {session, when, role, snippet, line_no}."""
    sessions_dir = get_project_sessions_dir(cwd)
    if not sessions_dir.exists():
        return []

    pattern = re.compile(re.escape(query), re.IGNORECASE)
    results: list[dict] = []

    for session_file in sorted(
        sessions_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True
    ):
        if len(results) >= max_results:
            break

        session_meta = parse_session_file(session_file)

        try:
            with open(session_file, "r", encoding="utf-8") as f:
                for line_no, raw in enumerate(f, 1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        entry = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    etype = entry.get("type", "")
                    role = entry.get("role") or etype
                    if role not in ("human", "user", "assistant"):
                        continue

                    # Date filter
                    if since:
                        ts = entry.get("timestamp") or entry.get("ts")
                        when = _parse_ts(ts)
                        if when and when < since:
                            continue
                    else:
                        ts = entry.get("timestamp") or entry.get("ts")
                        when = _parse_ts(ts)

                    content = entry.get("message", {}).get("content") or entry.get(
                        "content", ""
                    )
                    text = _extract_text(content)
                    if not text:
                        continue

                    if not pattern.search(text):
                        continue

                    # Build a snippet around the first match
                    match = pattern.search(text)
                    start = max(0, match.start() - 60)
                    end = min(len(text), match.end() + 60)
                    snippet = text[start:end].replace("\n", " ")
                    if start > 0:
                        snippet = "..." + snippet
                    if end < len(text):
                        snippet = snippet + "..."

                    results.append(
                        {
                            "session": session_meta,
                            "when": when,
                            "role": "user"
                            if role in ("human", "user")
                            else "assistant",
                            "snippet": snippet,
                            "line_no": line_no,
                        }
                    )

                    if len(results) >= max_results:
                        break

        except (IOError, PermissionError):
            continue

    return results


def cmd_search(sessions: list[dict], args) -> None:
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

    cwd = args.cwd or __import__("os").getcwd()
    results = search_sessions(cwd, query, since=since, max_results=args.limit)

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

    prev_sid = None
    for r in results:
        sid = r["session"]["session_id"]
        # Group header per session
        if sid != prev_sid:
            label = r["session"]["custom_title"] or r["session"]["label"] or sid[:16]
            date_str = (
                r["session"]["created_at"].strftime("%Y-%m-%d %H:%M")
                if r["session"]["created_at"]
                else "?"
            )
            print(
                f"  {CYAN}{sid[:16]}{RESET}  {GREEN}{label[:50]}{RESET}  {DIM}{date_str}{RESET}"
            )
            prev_sid = sid

        when_str = r["when"].strftime("%H:%M:%S") if r["when"] else "       "
        role_tag = (
            f"{CYAN}you{RESET}" if r["role"] == "user" else f"{YELLOW}claude{RESET}"
        )
        highlighted = _highlight(r["snippet"], pattern)
        print(f"    {DIM}{when_str}{RESET}  {role_tag}  {highlighted}")

    print(f"\n  {DIM}Preview a session:{RESET}  claudetool preview <session-id>")
