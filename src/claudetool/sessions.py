"""
Session data layer — parsing, listing, resolving, and deleting Claude Code sessions.

This module handles the filesystem operations on JSONL session files stored
under ``<config dir>/projects/<encoded-path>/``
(``$CLAUDE_CONFIG_DIR``, default ``~/.claude``).  It contains no ANSI formatting,
no argparse, and no template data.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003
from typing import Any, TypedDict

from claudetool._cache import load_summary, store_summary
from claudetool.rendering import RED, RESET
from claudetool.templates import claude_config_dir
from claudetool.transcript import Kind, parse_entries, parse_transcript

_TAIL_WINDOWS = (256 * 1024, 4 * 1024 * 1024)
_HEAD_BYTES = 2 * 1024 * 1024
_LABEL_CHARS = 80
_BRANCH_RE = re.compile(rb'"gitBranch":\s*"([^"]*)"')


# ─────────────────────────────────────────────
# Core helpers
# ─────────────────────────────────────────────


def encode_path(path: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "-", path)


def get_project_sessions_dir(cwd: str | None = None) -> Path:
    cwd = cwd or os.getcwd()
    encoded = encode_path(cwd)
    return claude_config_dir() / "projects" / encoded


# ─────────────────────────────────────────────
# Listing
# ─────────────────────────────────────────────


class Session(TypedDict):
    """One session as listed; `prompt_count` and `total_cost` fill in lazily."""

    session_id: str
    file: Path
    last_active: datetime
    custom_title: str | None
    label: str
    git_branch: str
    file_size_kb: float
    subagent_count: int
    prompt_count: int | None
    total_cost: float | None


@dataclass(frozen=True, slots=True)
class Subagent:
    """A subagent transcript owned by a session."""

    agent_id: str
    file: Path
    description: str
    agent_type: str
    model: str


def _tail_summary(path: Path) -> tuple[str | None, str]:
    """Return the last custom title and git branch found near the file end."""
    size = path.stat().st_size
    title: str | None = None
    branch = ""
    with path.open("rb") as fh:
        for window in _TAIL_WINDOWS:
            offset = max(0, size - window)
            fh.seek(offset)
            lines = fh.read().split(b"\n")
            if offset:
                lines = lines[1:]
            if not branch:
                branch = _last_branch(lines)
            title = _last_title(lines)
            if title is not None or offset == 0:
                break
    return title, branch


def _last_branch(lines: list[bytes]) -> str:
    for line in reversed(lines):
        found = _BRANCH_RE.search(line)
        if found:
            return found.group(1).decode("utf-8", "replace")
    return ""


def _last_title(lines: list[bytes]) -> str | None:
    for line in reversed(lines):
        if b"custom-title" not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("type") == "custom-title":
            title = str(entry.get("customTitle", "")).strip()
            if title:
                return title
    return None


def _first_prompt(path: Path) -> str:
    """Return the first user message, decoding only the head of the file."""
    with path.open("rb") as fh:
        head = fh.read(_HEAD_BYTES)
    lines = head.split(b"\n")
    if len(head) == _HEAD_BYTES:
        lines.pop()
    entries: list[dict[str, Any]] = []
    for line in lines:
        if b'"user"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    for block in parse_entries(entries):
        if block.kind is Kind.USER:
            return " ".join(block.text.split())[:_LABEL_CHARS]
    return ""


def _subagent_files(session_file: Path) -> list[Path]:
    root = session_file.with_suffix("") / "subagents"
    return sorted(root.glob("**/agent-*.jsonl")) if root.is_dir() else []


def _summarize(session_file: Path) -> Session:
    stat = session_file.stat()
    title, branch = _tail_summary(session_file)
    return {
        "session_id": session_file.stem,
        "file": session_file,
        "last_active": datetime.fromtimestamp(stat.st_mtime),  # noqa: DTZ006
        "custom_title": title,
        "label": title or _first_prompt(session_file),
        "git_branch": branch,
        "file_size_kb": round(stat.st_size / 1024, 1),
        "subagent_count": len(_subagent_files(session_file)),
        "prompt_count": None,
        "total_cost": None,
    }


def list_sessions_filesystem(cwd: str | None = None) -> list[Session]:
    """List the project's sessions, newest first, without parsing whole files."""
    sessions_dir = get_project_sessions_dir(cwd)
    if not sessions_dir.exists():
        print(f"No sessions directory found at: {sessions_dir}")
        return []
    files = sorted(
        sessions_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True
    )
    return [_summarize(f) for f in files]


def _signature(session_file: Path) -> str:
    stat = session_file.stat()
    subs = [f.stat().st_mtime_ns for f in _subagent_files(session_file)]
    return f"{stat.st_mtime_ns}:{stat.st_size}:{len(subs)}:{max(subs, default=0)}"


def enrich_session(session: Session) -> None:
    """Fill `prompt_count` and `total_cost`, reusing the cache when unchanged."""
    # Deferred: stats imports this module.
    from claudetool.stats import session_cost  # noqa: PLC0415

    path = session["file"]
    key, sig = str(path), _signature(path)
    cached = load_summary(key, sig)
    if cached is None:
        blocks = parse_transcript(path)
        count = sum(b.kind is Kind.USER for b in blocks)
        cost = session_cost(path)
        store_summary(key, sig, prompt_count=count, total_cost=cost)
    else:
        count, cost = cached["prompt_count"], cached["total_cost"]
    session["prompt_count"] = count
    session["total_cost"] = cost


def _read_meta(agent_file: Path) -> dict[str, Any]:
    meta = agent_file.with_suffix(".meta.json")
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def list_subagents(session_file: Path) -> list[Subagent]:
    """List the session's subagents, oldest first; missing metadata reads as empty."""
    files = sorted(_subagent_files(session_file), key=lambda f: f.stat().st_mtime)
    result = []
    for f in files:
        meta = _read_meta(f)
        result.append(
            Subagent(
                agent_id=f.stem.removeprefix("agent-"),
                file=f,
                description=str(meta.get("description", "")),
                agent_type=str(meta.get("agentType", "")),
                model=str(meta.get("model", "")),
            )
        )
    return result


def subagent_file(session_file: Path, agent_id: str) -> Path | None:
    """Return the transcript of subagent `agent_id`, if it exists."""
    for sub in list_subagents(session_file):
        if sub.agent_id == agent_id:
            return sub.file
    return None


# ─────────────────────────────────────────────
# Delete helpers
# ─────────────────────────────────────────────


def confirm(prompt: str) -> bool:
    ans = input(f"{RED}{prompt}{RESET} [y/N] ").strip().lower()
    return ans in ("y", "yes")


def delete_session_files(session_file: Path) -> None:
    """Remove a session transcript and its sibling subagent/tool-result dir."""
    session_file.unlink()
    shutil.rmtree(session_file.with_suffix(""), ignore_errors=True)


def delete_sessions(sessions: list[Session], dry_run: bool = False) -> int:
    deleted = 0
    for s in sessions:
        path = s["file"]
        side_dir = path.with_suffix("")
        label = s["custom_title"] or s["session_id"]
        suffix = f" + {side_dir.name}/" if side_dir.is_dir() else ""
        if dry_run:
            print(f"  [dry-run] Would delete: {label}  ({path.name}{suffix})")
            continue
        try:
            delete_session_files(path)
        except OSError as e:
            print(f"  [error] Could not delete {path.name}: {e}")
            continue
        print(f"  {RED}Deleted{RESET}: {label}  ({path.name}{suffix})")
        deleted += 1
    return deleted


def rename_session(session: Session, new_title: str) -> None:
    """Append a custom-title entry to the session JSONL and update the dict in-place."""
    entry = {
        "type": "custom-title",
        "customTitle": new_title.strip(),
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "uuid": str(uuid.uuid4()),
        "sessionId": session["session_id"],
    }
    with session["file"].open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    session["custom_title"] = new_title.strip()
    session["label"] = new_title.strip()


def resolve_targets(sessions: list[Session], ids_or_titles: list[str]) -> list[Session]:
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
