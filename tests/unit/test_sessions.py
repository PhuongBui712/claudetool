from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from _fixtures import assistant, user, write_jsonl

from claudetool.sessions import (
    delete_session_files,
    list_sessions_filesystem,
    list_subagents,
    rename_session,
    subagent_file,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def proj(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    return tmp_path / "cfg" / "projects" / "-p"


def _title(t: str) -> dict[str, str]:
    return {"type": "custom-title", "customTitle": t}


def test_summary_uses_last_custom_title_and_branch(proj: Path) -> None:
    write_jsonl(
        proj / "s.jsonl",
        [
            _title("old"),
            user("hello", gitBranch="main"),
            _title("new"),
            assistant("x") | {"gitBranch": "feat/x"},
        ],
    )
    [s] = list_sessions_filesystem("/p")
    assert (s["custom_title"], s["label"], s["git_branch"]) == ("new", "new", "feat/x")
    assert s["prompt_count"] is None
    assert s["total_cost"] is None


def test_summary_label_skips_meta_and_tool_results(proj: Path) -> None:
    result = user("ignored", "r")
    result["message"]["content"] = [
        {"type": "tool_result", "tool_use_id": "t", "content": "out"}
    ]
    write_jsonl(
        proj / "s.jsonl",
        [
            user("<system-reminder>x</system-reminder>", isMeta=True),
            result,
            user("the real  prompt\nhere", "u2"),
        ],
    )
    [s] = list_sessions_filesystem("/p")
    assert s["custom_title"] is None
    assert s["label"] == "the real prompt here"


def test_summary_label_is_capped_and_empty_without_prompt(proj: Path) -> None:
    write_jsonl(proj / "a.jsonl", [user("x" * 200)])
    write_jsonl(proj / "b.jsonl", [assistant("only agent")])
    labels = {s["session_id"]: s["label"] for s in list_sessions_filesystem("/p")}
    assert labels == {"a": "x" * 80, "b": ""}


def test_title_found_beyond_first_tail_window(proj: Path) -> None:
    filler = [assistant("y" * 1000, msg_id=None) for _ in range(400)]
    write_jsonl(proj / "s.jsonl", [_title("deep"), *filler])
    [s] = list_sessions_filesystem("/p")
    assert s["custom_title"] == "deep"


def test_list_subagents_reads_meta_and_tolerates_missing(proj: Path) -> None:
    session = write_jsonl(proj / "s.jsonl", [user("hi")])
    sub = proj / "s" / "subagents"
    write_jsonl(sub / "agent-a1.jsonl", [user("x")])
    (sub / "agent-a1.meta.json").write_text(
        json.dumps({"agentType": "Explore", "description": "look", "model": "haiku"})
    )
    write_jsonl(sub / "workflows" / "wf_1" / "agent-b2.jsonl", [user("y")])
    subs = {x.agent_id: x for x in list_subagents(session)}
    assert (subs["a1"].agent_type, subs["a1"].description, subs["a1"].model) == (
        "Explore",
        "look",
        "haiku",
    )
    assert subs["b2"].description == ""
    assert subagent_file(session, "b2") == subs["b2"].file
    assert subagent_file(session, "zz") is None


def test_delete_session_files_removes_sibling_dir(proj: Path) -> None:
    session = write_jsonl(proj / "s.jsonl", [user("hi")])
    write_jsonl(proj / "s" / "subagents" / "agent-a.jsonl", [user("x")])
    delete_session_files(session)
    assert not session.exists()
    assert not (proj / "s").exists()


def test_rename_session_sets_resume_title_and_prompt_footer_name(proj: Path) -> None:
    write_jsonl(proj / "s.jsonl", [_title("old"), user("hello")])
    [s] = list_sessions_filesystem("/p")

    rename_session(s, "  new name ")

    lines = (proj / "s.jsonl").read_text(encoding="utf-8").splitlines()
    tail = [json.loads(line) for line in lines[-2:]]
    assert [(e["type"], e.get("customTitle") or e.get("agentName")) for e in tail] == [
        ("custom-title", "new name"),
        ("agent-name", "new name"),
    ]
    assert all(e["sessionId"] == s["session_id"] for e in tail)
    assert (s["custom_title"], s["label"]) == ("new name", "new name")
