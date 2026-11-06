"""Tiny JSON cache of per-session summaries, keyed by session file path."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["load_summary", "store_summary"]


def _cache_file() -> Path:
    raw = os.environ.get("XDG_CACHE_HOME", "").strip()
    base = Path(raw).expanduser() if raw else Path.home() / ".cache"
    return base / "claudetool" / "summaries.json"


def _read_all() -> dict[str, Any]:
    try:
        data = json.loads(_cache_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_summary(key: str, signature: str) -> dict[str, Any] | None:
    """Return the cached summary for `key`, or None if absent or stale."""
    entry = _read_all().get(key)
    if isinstance(entry, dict) and entry.get("signature") == signature:
        return entry
    return None


def store_summary(key: str, signature: str, **values: Any) -> None:  # noqa: ANN401
    """Save `values` for `key` atomically; a failed write is silently skipped."""
    path = _cache_file()
    data = _read_all()
    data[key] = {"signature": signature, **values}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        Path(tmp).replace(path)
    except OSError:
        pass
