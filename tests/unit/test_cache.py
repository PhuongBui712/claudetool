from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from _fixtures import assistant, user, write_jsonl

from claudetool import sessions as sessions_mod
from claudetool._cache import load_summary, store_summary
from claudetool.sessions import enrich_session, list_sessions_filesystem

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))


def test_store_then_load_roundtrips() -> None:
    store_summary("k", "sig", prompt_count=3)
    assert load_summary("k", "sig") == {"signature": "sig", "prompt_count": 3}


def test_load_misses_on_other_signature_or_key() -> None:
    store_summary("k", "sig", prompt_count=3)
    assert load_summary("k", "other") is None
    assert load_summary("nope", "sig") is None


def test_corrupt_cache_is_treated_as_empty(tmp_path: Path) -> None:
    store_summary("k", "sig", prompt_count=3)
    (tmp_path / "cache" / "claudetool" / "summaries.json").write_text("{nope")
    assert load_summary("k", "sig") is None
    store_summary("k", "sig", prompt_count=4)
    assert load_summary("k", "sig") is not None


def _one_session(tmp_path: Path) -> Path:
    proj = tmp_path / "cfg" / "projects" / "-p"
    return write_jsonl(
        proj / "s.jsonl", [user("hi"), assistant("yo"), user("again", "u2")]
    )


def test_enrich_fills_prompts_and_cost_and_uses_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _one_session(tmp_path)
    [s] = list_sessions_filesystem("/p")
    enrich_session(s)
    assert s["prompt_count"] == 2
    assert s["total_cost"] == pytest.approx(15.0)

    def boom(*_a: object, **_k: object) -> None:
        msg = "cache miss"
        raise AssertionError(msg)

    monkeypatch.setattr(sessions_mod, "parse_transcript", boom)
    [again] = list_sessions_filesystem("/p")
    enrich_session(again)
    assert again["prompt_count"] == 2


def test_touching_a_subagent_file_invalidates_cache(tmp_path: Path) -> None:
    session = _one_session(tmp_path)
    [s] = list_sessions_filesystem("/p")
    enrich_session(s)
    sub = write_jsonl(
        session.with_suffix("") / "subagents" / "agent-x.jsonl", [assistant("z")]
    )
    [s2] = list_sessions_filesystem("/p")
    assert s2["subagent_count"] == 1
    enrich_session(s2)
    assert s2["total_cost"] == pytest.approx(30.0)
    sub.write_text(sub.read_text() * 2)
    [s3] = list_sessions_filesystem("/p")
    enrich_session(s3)
    assert s3["total_cost"] == pytest.approx(30.0)
