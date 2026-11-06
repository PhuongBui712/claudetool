from __future__ import annotations

from typing import TYPE_CHECKING

from _fixtures import assistant, user, write_jsonl

from claudetool.search import search_sessions
from claudetool.transcript import Kind

if TYPE_CHECKING:
    from pathlib import Path


def _tool_use() -> dict:
    e = assistant("running", uuid="a-tool")
    e["message"]["content"].append(
        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}
    )
    return e


def _tool_result(text: str) -> dict:
    e = user("", "r1")
    e["message"]["content"] = [
        {"type": "tool_result", "tool_use_id": "t1", "content": text}
    ]
    e["sourceToolAssistantUUID"] = "a-tool"
    return e


def test_search_ignores_bookkeeping_lines(tmp_path: Path) -> None:
    f = write_jsonl(
        tmp_path / "s.jsonl",
        [
            {"type": "attachment", "uuid": "x", "content": "needle in attachment"},
            {"type": "file-history-snapshot", "note": "needle"},
            user("a needle here", "u1"),
        ],
    )
    hits = list(search_sessions([f], "NEEDLE"))
    assert [(h.uuid, h.kind) for h in hits] == [("u1", Kind.USER)]
    assert "needle" in hits[0].snippet


def test_search_maps_tool_result_to_source_assistant_uuid(tmp_path: Path) -> None:
    f = write_jsonl(tmp_path / "s.jsonl", [_tool_use(), _tool_result("found needle")])
    [hit] = search_sessions([f], "needle")
    assert (hit.uuid, hit.kind) == ("a-tool", Kind.TOOL)


def test_search_matches_tool_input(tmp_path: Path) -> None:
    f = write_jsonl(tmp_path / "s.jsonl", [_tool_use()])
    [hit] = search_sessions([f], "ls")
    assert hit.kind in (Kind.TOOL, Kind.AGENT)


def test_search_honours_max_results_across_files(tmp_path: Path) -> None:
    files = [
        write_jsonl(tmp_path / f"{n}.jsonl", [user("needle", "a"), user("needle", "b")])
        for n in "xy"
    ]
    assert len(list(search_sessions(files, "needle", max_results=3))) == 3


def test_search_stops_when_cancelled(tmp_path: Path) -> None:
    f = write_jsonl(tmp_path / "s.jsonl", [user("needle")])
    assert list(search_sessions([f], "needle", cancelled=lambda: True)) == []
