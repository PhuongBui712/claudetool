"""Helpers to build tiny transcript fixtures."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


def write_jsonl(path: Path, entries: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(e, separators=(",", ":")) for e in entries) + "\n"
    )
    return path


def user(text: str, uuid: str = "u", **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    return {
        "type": "user",
        "uuid": uuid,
        "timestamp": "2026-01-02T03:04:05Z",
        "message": {"role": "user", "content": text},
        **extra,
    }


def assistant(
    text: str,
    uuid: str = "a",
    msg_id: str | None = "m1",
    out: int = 1_000_000,
    model: str = "claude-sonnet-4",
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 0, "output_tokens": out},
    }
    if msg_id:
        message["id"] = msg_id
    return {
        "type": "assistant",
        "uuid": uuid,
        "timestamp": "2026-01-02T03:04:06Z",
        "message": message,
    }
