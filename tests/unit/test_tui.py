"""Headless tests of the Textual UI: list, search, viewer, and exits."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest
from _fixtures import write_jsonl
from rich.segment import Segment
from textual.strip import Strip
from textual.widgets import Input, OptionList

from claudetool._screens import SessionListScreen, session_viewer
from claudetool._viewer import _MATCH, TranscriptView, ViewerScreen, _clean, _highlight
from claudetool.sessions import list_sessions_filesystem
from claudetool.transcript import Kind
from claudetool.tui import _ClaudeTool, run_interactive

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    from textual.pilot import Pilot
    from textual.screen import Screen

    from claudetool.sessions import Session

_SIZE = (100, 30)


def _assistant(uuid: str, *content: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "assistant",
        "uuid": uuid,
        "timestamp": "2026-01-02T03:04:06Z",
        "message": {"role": "assistant", "content": list(content)},
    }


def _user(uuid: str, content: object, **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    return {
        "type": "user",
        "uuid": uuid,
        "timestamp": "2026-01-02T03:04:05Z",
        "message": {"role": "user", "content": content},
        **extra,
    }


def _result(tool_id: str, text: str) -> list[dict[str, Any]]:
    return [{"type": "tool_result", "tool_use_id": tool_id, "content": text}]


def _transcript() -> list[dict[str, Any]]:
    """User (5 lines), thinking, agent, Bash, Agent call, result."""
    agent_input = {"description": "Map things", "subagent_type": "Explore"}
    return [
        _user("u1", "first line\nsecond\nthird\nfourth\nfifth"),
        _assistant("a1", {"type": "thinking", "thinking": "secret pondering"}),
        _assistant("a2", {"type": "text", "text": "Looking around"}),
        _assistant(
            "a3",
            {
                "type": "tool_use",
                "id": "t1",
                "name": "Bash",
                "input": {"command": "ls"},
            },
        ),
        _user("r1", _result("t1", "alpha.txt\nbeta.txt\ngamma.txt")),
        _assistant(
            "a4",
            {"type": "tool_use", "id": "t2", "name": "Agent", "input": agent_input},
        ),
        _user("r2", _result("t2", "report"), toolUseResult={"agentId": "abc123"}),
        _assistant("a5", {"type": "text", "text": "All **done** here"}),
    ]


@pytest.fixture
def sessions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[Session]:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    project = tmp_path / "cfg" / "projects" / "-proj-demo"
    main = write_jsonl(project / "s1.jsonl", _transcript())
    write_jsonl(project / "s2.jsonl", [_user("x1", "other topic")])
    subagents = main.with_suffix("") / "subagents"
    write_jsonl(
        subagents / "agent-abc123.jsonl",
        [_user("s1", "sub prompt"), _assistant("s2", {"type": "text", "text": "sub"})],
    )
    meta = {"description": "Map things", "agentType": "Explore", "model": "sonnet"}
    (subagents / "agent-abc123.meta.json").write_text(json.dumps(meta))
    return list_sessions_filesystem("/proj/demo")


def _drive(
    first: Callable[[], Screen[None]],
    scenario: Callable[[Pilot[None]], Awaitable[None]],
) -> _ClaudeTool:
    async def main() -> _ClaudeTool:
        app = _ClaudeTool(first())
        async with app.run_test(size=_SIZE) as pilot:
            await _settle(pilot)
            await scenario(pilot)
        return app

    return asyncio.run(main())


async def _settle(pilot: Pilot[None]) -> None:
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


def _list_screen(sessions: list[Session]) -> Callable[[], Screen[None]]:
    return lambda: SessionListScreen(sessions, "/proj/demo")


def _viewer(session: Session) -> Callable[[], Screen[None]]:
    return lambda: session_viewer(session, "demo")


def _view(pilot: Pilot[None]) -> TranscriptView:
    return pilot.app.screen.query_one(TranscriptView)


def _kind(view: TranscriptView) -> Kind:
    # A fresh read each call: mypy narrows `view.focused.kind` after an assert.
    assert view.focused is not None
    return view.focused.kind


def _screen_text(view: TranscriptView) -> str:
    return "\n".join(view.render_line(y).text for y in range(view.size.height))


def _main(sessions: list[Session]) -> Session:
    return next(s for s in sessions if s["session_id"] == "s1")


def test_ctrl_c_exits_from_session_list(sessions: list[Session]) -> None:
    async def scenario(pilot: Pilot[None]) -> None:
        await pilot.press("ctrl+c")

    assert _drive(_list_screen(sessions), scenario).return_code == 130


def test_ctrl_c_exits_from_viewer(sessions: list[Session]) -> None:
    async def scenario(pilot: Pilot[None]) -> None:
        await pilot.press("enter")
        await _settle(pilot)
        assert isinstance(pilot.app.screen, ViewerScreen)
        await pilot.press("ctrl+c")

    assert _drive(_list_screen(sessions), scenario).return_code == 130


@pytest.mark.parametrize("opener", ["list_filter", "viewer_find", "content_search"])
def test_ctrl_c_exits_while_an_input_has_focus(
    sessions: list[Session], opener: str
) -> None:
    first = _viewer(_main(sessions)) if opener == "viewer_find" else None
    first = first or _list_screen(sessions)

    async def scenario(pilot: Pilot[None]) -> None:
        await pilot.press("ctrl+f" if opener == "content_search" else "slash")
        await pilot.press("q", "x")
        assert isinstance(pilot.app.focused, Input)
        assert pilot.app.focused.value == "qx"
        await pilot.press("ctrl+c")

    assert _drive(first, scenario).return_code == 130


def test_q_on_session_list_quits_with_status_zero(sessions: list[Session]) -> None:
    async def scenario(pilot: Pilot[None]) -> None:
        await pilot.press("q")

    assert _drive(_list_screen(sessions), scenario).return_code == 0


def test_viewer_opens_focused_on_last_block(sessions: list[Session]) -> None:
    async def scenario(pilot: Pilot[None]) -> None:
        view = _view(pilot)
        assert view.focused is not None
        assert view.focused.kind is Kind.RESULT
        assert view.position == (5, 5)

    _drive(_viewer(_main(sessions)), scenario)


def test_j_and_k_move_focus_by_block_not_line(sessions: list[Session]) -> None:
    async def scenario(pilot: Pilot[None]) -> None:
        view = _view(pilot)
        await pilot.press("g")
        assert view.focused is not None
        assert view.focused.kind is Kind.USER
        await pilot.press("j")
        assert _kind(view) is Kind.AGENT
        await pilot.press("j", "j")
        assert view.focused.tool_name == "Agent"
        await pilot.press("k")
        assert view.focused.tool_name == "Bash"

    _drive(_viewer(_main(sessions)), scenario)


def test_ctrl_o_toggles_thinking_and_tool_output_keeping_focus(
    sessions: list[Session],
) -> None:
    async def scenario(pilot: Pilot[None]) -> None:
        view = _view(pilot)
        await pilot.press("g", "j", "j")
        focused = view.focused
        assert focused is not None
        assert focused.tool_name == "Bash"
        collapsed = _screen_text(view)
        assert "secret pondering" not in collapsed
        assert "beta.txt" not in collapsed
        assert "3 lines" in collapsed

        await pilot.press("ctrl+o")
        expanded = _screen_text(view)
        assert view.expanded
        assert "secret pondering" in expanded
        assert "beta.txt" in expanded
        assert view.focused is focused

        await pilot.press("ctrl+o")
        assert "secret pondering" not in _screen_text(view)
        assert view.focused is focused

    _drive(_viewer(_main(sessions)), scenario)


def test_enter_on_agent_opens_subagent_and_escape_restores_focus(
    sessions: list[Session],
) -> None:
    async def scenario(pilot: Pilot[None]) -> None:
        parent = pilot.app.screen
        await pilot.press("k")
        focused = _view(pilot).focused
        assert focused is not None
        assert focused.agent_id == "abc123"

        await pilot.press("enter")
        await _settle(pilot)
        assert pilot.app.screen is not parent
        assert "sub prompt" in _screen_text(_view(pilot))

        await pilot.press("escape")
        await pilot.pause()
        assert pilot.app.screen is parent
        assert _view(pilot).focused is focused

    _drive(_viewer(_main(sessions)), scenario)


def test_a_lists_subagents_and_opens_the_picked_one(sessions: list[Session]) -> None:
    async def scenario(pilot: Pilot[None]) -> None:
        await pilot.press("a")
        await pilot.pause()
        assert pilot.app.screen.query_one(OptionList).option_count == 1
        await pilot.press("enter")
        await _settle(pilot)
        assert "sub prompt" in _screen_text(_view(pilot))

    _drive(_viewer(_main(sessions)), scenario)


def test_slash_search_and_n_jump_to_matching_blocks(sessions: list[Session]) -> None:
    async def scenario(pilot: Pilot[None]) -> None:
        view = _view(pilot)
        await pilot.press("slash", *"TXT", "enter")
        assert view.focused is not None
        assert view.focused.tool_name == "Bash"
        assert not view.expanded

        await pilot.press("slash", *"done", "enter")
        assert _kind(view) is Kind.RESULT
        await pilot.press("slash", *"line", "enter")
        assert _kind(view) is Kind.USER
        await pilot.press("n")
        assert _kind(view) is Kind.USER

    _drive(_viewer(_main(sessions)), scenario)


def test_search_match_in_hidden_kind_switches_to_expanded(
    sessions: list[Session],
) -> None:
    async def scenario(pilot: Pilot[None]) -> None:
        view = _view(pilot)
        await pilot.press("slash", *"pondering", "enter")
        assert view.expanded
        assert view.focused is not None
        assert view.focused.kind is Kind.THINKING

    _drive(_viewer(_main(sessions)), scenario)


def test_filter_narrows_the_session_list(sessions: list[Session]) -> None:
    async def scenario(pilot: Pilot[None]) -> None:
        options = pilot.app.screen.query_one(OptionList)
        assert options.option_count == 2
        await pilot.press("slash", *"other")
        assert options.option_count == 1
        await pilot.press("escape")
        assert options.option_count == 2

    _drive(_list_screen(sessions), scenario)


def test_session_rows_fill_prompts_and_cost_from_enrichment(
    sessions: list[Session],
) -> None:
    async def scenario(pilot: Pilot[None]) -> None:
        del pilot
        assert all(s["prompt_count"] is not None for s in sessions)

    _drive(_list_screen(sessions), scenario)


@pytest.mark.parametrize(("answer", "remaining"), [("y", 1), ("n", 2), ("escape", 2)])
def test_delete_removes_row_only_when_confirmed(
    sessions: list[Session], answer: str, remaining: int
) -> None:
    files = [s["file"] for s in sessions]

    async def scenario(pilot: Pilot[None]) -> None:
        await pilot.press("d")
        await pilot.press(answer)
        await pilot.pause()
        assert pilot.app.screen.query_one(OptionList).option_count == remaining

    _drive(_list_screen(sessions), scenario)
    assert sum(f.exists() for f in files) == remaining


def test_rename_updates_title(sessions: list[Session]) -> None:
    async def scenario(pilot: Pilot[None]) -> None:
        await pilot.press("r")
        await pilot.press("ctrl+a", *"Fresh", "enter")
        await pilot.pause()

    _drive(_list_screen(sessions), scenario)
    assert sessions[0]["custom_title"] == "Fresh"
    assert "Fresh" in sessions[0]["file"].read_text()


def test_content_search_opens_viewer_on_hit(sessions: list[Session]) -> None:
    async def scenario(pilot: Pilot[None]) -> None:
        await pilot.press("ctrl+f", *"Looking", "enter")
        await _settle(pilot)
        assert pilot.app.screen.query_one(OptionList).option_count == 1
        await pilot.press("enter")
        await _settle(pilot)
        focused = _view(pilot).focused
        assert focused is not None
        assert focused.text == "Looking around"

    _drive(_list_screen(sessions), scenario)


def test_run_interactive_exits_130_on_ctrl_c(
    sessions: list[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(app: _ClaudeTool) -> None:
        app.exit(return_code=130)

    monkeypatch.setattr(_ClaudeTool, "run", fake_run)
    with pytest.raises(SystemExit) as exited:
        run_interactive(sessions, "/proj/demo")
    assert exited.value.code == 130


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("\x1b[31mred\x1b[0m", "red"),
        ("a\tb", "a   b"),
        ("bell\x07 cr\r", "bell cr"),
        ("\x1b]0;title\x07text", "text"),
        ("ünïcode ✓", "ünïcode ✓"),
    ],
)
def test_clean_strips_terminal_controls(raw: str, clean: str) -> None:
    assert _clean(raw) == clean


def test_highlight_marks_every_case_insensitive_match() -> None:
    strip = Strip([Segment("alpha TXT "), Segment("beta txt")])
    marked = [seg.text for seg in _highlight(strip, "txt") if seg.style == _MATCH]
    assert marked == ["TXT", "txt"]


def test_highlight_leaves_strip_without_match_untouched() -> None:
    strip = Strip([Segment("nothing here")])
    assert _highlight(strip, "txt") is strip


def test_viewer_handles_empty_transcript(sessions: list[Session]) -> None:
    session = _main(sessions)
    session["file"].write_text("")

    async def scenario(pilot: Pilot[None]) -> None:
        view = _view(pilot)
        assert view.focused is None
        assert view.position == (0, 0)
        await pilot.press("j", "k", "ctrl+o", "G", "pagedown")
        await pilot.press("slash", *"x", "enter", "n")

    _drive(_viewer(session), scenario)
