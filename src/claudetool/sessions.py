"""
Session data layer — parsing, listing, resolving, and deleting Claude Code sessions.

This module handles the filesystem operations on JSONL session files stored
under ``~/.claude/projects/<encoded-path>/``.  It contains no ANSI formatting,
no argparse, and no template data.
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime

from claudetool.rendering import RED, RESET


# ─────────────────────────────────────────────
# Core helpers
# ─────────────────────────────────────────────


def encode_path(path: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "-", path)


def get_project_sessions_dir(cwd: str | None = None) -> Path:
    cwd = cwd or os.getcwd()
    encoded = encode_path(cwd)
    return Path.home() / ".claude" / "projects" / encoded


# ─────────────────────────────────────────────
# Session-level parsing
# ─────────────────────────────────────────────


def parse_session_file(session_file: Path) -> dict:
    first_user_msg = None
    custom_title = None
    last_timestamp = None
    total_lines = 0

    try:
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total_lines += 1
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if entry.get("type") == "custom-title":
                    title = entry.get("customTitle", "").strip()
                    if title:
                        custom_title = title

                ts = entry.get("timestamp") or entry.get("ts")
                if ts:
                    last_timestamp = ts

                if first_user_msg is None:
                    role = entry.get("role") or entry.get("type")
                    content = entry.get("message", {}).get("content") or entry.get(
                        "content", ""
                    )
                    if role in ("human", "user"):
                        if isinstance(content, str):
                            first_user_msg = content.strip()
                        elif isinstance(content, list):
                            for block in content:
                                if (
                                    isinstance(block, dict)
                                    and block.get("type") == "text"
                                ):
                                    first_user_msg = block.get("text", "").strip()
                                    break

    except (IOError, PermissionError) as e:
        print(f"  [warn] Could not read {session_file.name}: {e}")

    created_at = None
    if last_timestamp:
        try:
            if isinstance(last_timestamp, (int, float)):
                created_at = datetime.fromtimestamp(last_timestamp / 1000)
            else:
                created_at = datetime.fromisoformat(
                    str(last_timestamp).replace("Z", "+00:00")
                )
        except Exception:
            pass
    if not created_at:
        created_at = datetime.fromtimestamp(session_file.stat().st_mtime)

    label = custom_title or (first_user_msg or "")[:80]

    # Lazy-load cost — computed on first access via stats module
    return {
        "session_id": session_file.stem,
        "file": session_file,
        "created_at": created_at,
        "message_count": total_lines,
        "custom_title": custom_title,
        "label": label,
        "file_size_kb": round(session_file.stat().st_size / 1024, 1),
        "total_cost": None,  # populated by enrich_with_costs()
    }


def list_sessions_filesystem(cwd: str | None = None) -> list[dict]:
    sessions_dir = get_project_sessions_dir(cwd)
    if not sessions_dir.exists():
        print(f"No sessions directory found at: {sessions_dir}")
        return []
    session_files = sorted(
        sessions_dir.glob("*.jsonl"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return [parse_session_file(f) for f in session_files]


# ─────────────────────────────────────────────
# Message-level parsing  (for preview)
# ─────────────────────────────────────────────


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")
            if btype == "text":
                parts.append(block.get("text", "").strip())
            elif btype == "tool_use":
                name = block.get("name", "tool")
                inp = block.get("input", {})
                brief = json.dumps(inp, ensure_ascii=False)[:120]
                parts.append(f"[tool_use: {name}] {brief}")
            elif btype == "tool_result":
                inner = block.get("content", "")
                brief = _extract_text(inner)[:120]
                parts.append(f"[tool_result] {brief}")
        return "\n".join(p for p in parts if p)
    return ""


def parse_messages(session_file: Path) -> list[dict]:
    messages = []
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = entry.get("type", "")
                if etype in ("custom-title", "summary"):
                    continue

                role = entry.get("role") or etype
                if role not in ("human", "user", "assistant"):
                    continue

                ts = entry.get("timestamp") or entry.get("ts")
                when = None
                if ts:
                    try:
                        if isinstance(ts, (int, float)):
                            when = datetime.fromtimestamp(ts / 1000)
                        else:
                            when = datetime.fromisoformat(
                                str(ts).replace("Z", "+00:00")
                            )
                    except Exception:
                        pass

                content = entry.get("message", {}).get("content") or entry.get(
                    "content", ""
                )
                text = _extract_text(content)
                if not text:
                    continue

                messages.append(
                    {
                        "role": "user" if role in ("human", "user") else "assistant",
                        "when": when,
                        "text": text,
                    }
                )
    except (IOError, PermissionError) as e:
        print(f"[warn] {e}")
    return messages


# ─────────────────────────────────────────────
# Delete helpers
# ─────────────────────────────────────────────


def confirm(prompt: str) -> bool:
    ans = input(f"{RED}{prompt}{RESET} [y/N] ").strip().lower()
    return ans in ("y", "yes")


def delete_sessions(sessions: list[dict], dry_run: bool = False) -> int:
    deleted = 0
    for s in sessions:
        path: Path = s["file"]
        label = s["custom_title"] or s["session_id"]
        if dry_run:
            print(f"  [dry-run] Would delete: {label}  ({path.name})")
        else:
            try:
                path.unlink()
                print(f"  {RED}Deleted{RESET}: {label}  ({path.name})")
                deleted += 1
            except OSError as e:
                print(f"  [error] Could not delete {path.name}: {e}")
    return deleted


def rename_session(session: dict, new_title: str) -> None:
    """Append a custom-title entry to the session JSONL and update the dict in-place."""
    import uuid as _uuid

    entry = {
        "type": "custom-title",
        "customTitle": new_title.strip(),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "uuid": str(_uuid.uuid4()),
        "sessionId": session["session_id"],
    }
    path: Path = session["file"]
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    session["custom_title"] = new_title.strip()
    session["label"] = new_title.strip()


def resolve_targets(sessions: list[dict], ids_or_titles: list[str]) -> list[dict]:
    targets = []
    needles = [t.lower() for t in ids_or_titles]
    for s in sessions:
        sid = s["session_id"].lower()
        title = (s["custom_title"] or "").lower()
        for needle in needles:
            if sid.startswith(needle) or (title and needle in title):
                targets.append(s)
                break
    return targets
