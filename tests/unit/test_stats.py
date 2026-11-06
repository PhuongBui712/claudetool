from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from _fixtures import assistant, write_jsonl

from claudetool.stats import extract_session_usage, session_cost

if TYPE_CHECKING:
    from pathlib import Path

# 1M sonnet output tokens cost $15.
ONE = 15.0


def test_usage_counts_each_message_id_once(tmp_path: Path) -> None:
    f = write_jsonl(
        tmp_path / "s.jsonl",
        [assistant("a", uuid="1"), assistant("b", uuid="2"), assistant("c", "3", "m2")],
    )
    usage = extract_session_usage(f)
    assert usage["totals"]["output_tokens"] == 2_000_000
    assert next(iter(usage["by_model"].values()))["requests"] == 2


def test_usage_counts_entries_without_id_individually(tmp_path: Path) -> None:
    f = write_jsonl(
        tmp_path / "s.jsonl",
        [assistant("a", msg_id=None), assistant("b", msg_id=None)],
    )
    assert extract_session_usage(f)["totals"]["output_tokens"] == 2_000_000


def test_session_cost_includes_subagents_by_default(tmp_path: Path) -> None:
    session = _with_subagent(tmp_path)
    assert session_cost(session) == pytest.approx(2 * ONE)


def test_session_cost_can_exclude_subagents(tmp_path: Path) -> None:
    session = _with_subagent(tmp_path)
    assert session_cost(session, include_subagents=False) == pytest.approx(ONE)


def _with_subagent(tmp_path: Path) -> Path:
    session = write_jsonl(tmp_path / "s.jsonl", [assistant("a")])
    write_jsonl(tmp_path / "s" / "subagents" / "agent-x.jsonl", [assistant("b")])
    return session
