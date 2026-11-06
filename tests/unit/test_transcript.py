"""Tests for parsing transcripts into blocks."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from claudetool.transcript import Block, Kind, parse_entries, parse_transcript

_SLASH_WITH_ARGS = (
    "<command-name>/quick</command-name>\n<command-message>quick</command-message>\n"
    "<command-args>check aws</command-args>"
)


def _dumps(entry: dict[str, Any]) -> str:
    # Claude Code writes compact JSON; the reader's byte prefilter relies on it.
    return json.dumps(entry, separators=(",", ":"))


def _agent(uuid: str, block: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "assistant",
        "uuid": uuid,
        "timestamp": "2026-11-06T10:00:00.000Z",
        "message": {"id": "msg_1", "content": [block]},
    }


def _text(uuid: str, text: str) -> dict[str, Any]:
    return _agent(uuid, {"type": "text", "text": text})


def _thinking(uuid: str) -> dict[str, Any]:
    return _agent(uuid, {"type": "thinking", "thinking": "hmm"})


def _tool_use(
    uuid: str,
    tool_input: dict[str, Any],
    *,
    name: str = "Bash",
    tool_id: str = "toolu_1",
) -> dict[str, Any]:
    block = {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}
    return _agent(uuid, block)


def _result(
    content: Any,  # noqa: ANN401
    *,
    tool_id: str = "toolu_1",
    is_error: bool = False,
    tool_use_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "type": "user",
        "uuid": "ur",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": content,
                    "is_error": is_error,
                }
            ]
        },
    }
    if tool_use_result is not None:
        entry["toolUseResult"] = tool_use_result
    return entry


def _user(content: Any, **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    return {"type": "user", "uuid": "u1", "message": {"content": content}, **extra}


def _kinds(entries: list[dict[str, Any]]) -> list[Kind]:
    return [b.kind for b in parse_entries(entries)]


def _only(entries: list[dict[str, Any]]) -> Block:
    blocks = parse_entries(entries)
    assert len(blocks) == 1
    return blocks[0]


# Result marking


def test_last_agent_message_of_turn_becomes_result() -> None:
    entries = [_user("go"), _text("a1", "one"), _text("a2", "two")]
    assert _kinds(entries) == [Kind.USER, Kind.AGENT, Kind.RESULT]


def test_single_agent_message_is_result() -> None:
    assert _kinds([_user("go"), _text("a1", "only")]) == [Kind.USER, Kind.RESULT]


def test_each_turn_gets_its_own_result() -> None:
    entries = [
        _user("one"),
        _text("a1", "x"),
        _text("a2", "y"),
        _user("two"),
        _text("a3", "z"),
    ]
    assert _kinds(entries) == [
        Kind.USER,
        Kind.AGENT,
        Kind.RESULT,
        Kind.USER,
        Kind.RESULT,
    ]


def test_turn_ending_on_tool_call_has_no_result() -> None:
    entries = [_user("go"), _text("a1", "running"), _tool_use("a2", {"command": "ls"})]
    assert _kinds(entries) == [Kind.USER, Kind.AGENT, Kind.TOOL]


def test_turn_ending_on_interruption_has_no_result() -> None:
    entries = [_user("go"), _text("a1", "wip"), _user("[Request interrupted by user]")]
    assert Kind.RESULT not in _kinds(entries)


@pytest.mark.parametrize(
    "trailer",
    [
        _thinking("a2"),
        _user("<system-reminder>x</system-reminder>"),
        _user("hi", isMeta=True),
    ],
)
def test_thinking_and_meta_after_last_agent_text_keep_result(
    trailer: dict[str, Any],
) -> None:
    kinds = _kinds([_user("go"), _text("a1", "done"), trailer])
    assert kinds[1] is Kind.RESULT


# Tool pairing


def test_tool_result_fills_output_and_error_flag() -> None:
    entries = [
        _tool_use("a1", {"command": "ls"}),
        _result("boom", is_error=True),
    ]
    block = _only(entries)
    assert (block.output, block.is_error) == ("boom", True)


def test_tool_call_without_result_has_empty_output() -> None:
    block = _only([_tool_use("a1", {"command": "ls"})])
    assert (block.output, block.is_error) == ("", False)


def test_tool_result_for_unknown_call_is_ignored() -> None:
    entries = [_tool_use("a1", {"command": "ls"}), _result("x", tool_id="nope")]
    assert _only(entries).output == ""


def test_tool_result_list_content_joins_text_and_image() -> None:
    content = [{"type": "text", "text": "see"}, {"type": "image", "source": {}}]
    block = _only([_tool_use("a1", {"command": "ls"}), _result(content)])
    assert block.output == "see\n[image]"


def test_tool_call_carries_name_input_json_uuid_and_timestamp() -> None:
    block = _only([_tool_use("a1", {"command": "ls"})])
    assert block.tool_name == "Bash"
    assert json.loads(block.text) == {"command": "ls"}
    assert block.uuid == "a1"
    assert block.timestamp == datetime(2026, 11, 6, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("tool_input", "expected"),
    [
        ({"command": "git status", "description": "d"}, "git status"),
        ({"description": "d", "file_path": "/a"}, "/a"),
        ({"pattern": "p", "description": "d"}, "p"),
        ({"description": "d", "prompt": "p"}, "d"),
        ({"prompt": "p"}, "p"),
        ({"command": "line1\nline2"}, "line1"),
        ({"command": "  \n"}, ""),
        ({"command": 3}, ""),
        ({"unrelated": "x"}, ""),
        ({}, ""),
    ],
)
def test_tool_summary_uses_highest_priority_key_first_line(
    tool_input: dict[str, Any], expected: str
) -> None:
    assert _only([_tool_use("a1", tool_input)]).summary == expected


def test_agent_id_comes_from_tool_use_result() -> None:
    entries = [
        _tool_use("a1", {"prompt": "p"}, name="Agent"),
        _result("launched", tool_use_result={"agentId": "abc123"}),
    ]
    assert _only(entries).agent_id == "abc123"


@pytest.mark.parametrize("name", ["Agent", "Task"])
def test_agent_id_falls_back_to_result_text(name: str) -> None:
    entries = [
        _tool_use("a1", {"prompt": "p"}, name=name),
        _result("done\nagentId: abc123 (use SendMessage)"),
    ]
    assert _only(entries).agent_id == "abc123"


def test_agent_id_empty_when_agent_result_has_no_id() -> None:
    entries = [_tool_use("a1", {"prompt": "p"}, name="Agent"), _result("done")]
    assert _only(entries).agent_id == ""


def test_agent_id_not_taken_from_text_for_other_tools() -> None:
    entries = [_tool_use("a1", {"command": "x"}), _result("agentId: abc123")]
    assert _only(entries).agent_id == ""


# User messages


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("fix the bug", "fix the bug"),
        (
            _SLASH_WITH_ARGS,
            "/quick check aws",
        ),
        (
            "<command-name>/quick</command-name>\n<command-args></command-args>",
            "/quick",
        ),
        ("<command-name>/clear</command-name>", "/clear"),
        ("<bash-input>ls</bash-input>", "! ls"),
        ("  padded  ", "padded"),
        ([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}], "a\nb"),
        (
            [{"type": "text", "text": "look"}, {"type": "image", "source": {}}],
            "look\n[image]",
        ),
        ([{"type": "image", "source": {}}], "[image]"),
    ],
)
def test_user_message_rendering(content: Any, expected: str) -> None:  # noqa: ANN401
    block = _only([_user(content)])
    assert (block.kind, block.text) == (Kind.USER, expected)


@pytest.mark.parametrize("content", ["", "   \n", [], None])
def test_empty_user_content_produces_no_block(content: Any) -> None:  # noqa: ANN401
    assert parse_entries([_user(content)]) == []


# Meta, interrupted, compacted, system


@pytest.mark.parametrize(
    "text",
    [
        "<task-notification>done</task-notification>",
        "<system-reminder>x</system-reminder>",
        "<local-command-stdout>out</local-command-stdout>",
        "<local-command-caveat>c</local-command-caveat>",
        "Another Claude session sent a message: hi",
    ],
)
def test_injected_prefixes_are_meta(text: str) -> None:
    assert _only([_user(text)]).kind is Kind.META


def test_is_meta_flag_makes_plain_text_meta() -> None:
    assert _only([_user("hello", isMeta=True)]).kind is Kind.META


@pytest.mark.parametrize(
    "text",
    ["[Request interrupted by user]", "[Request interrupted by user for tool use]"],
)
def test_interruption_text_is_interrupted(text: str) -> None:
    block = _only([_user([{"type": "text", "text": text}])])
    assert (block.kind, block.text) == (Kind.INTERRUPTED, text)


def test_compact_boundary_and_summary_merge_into_one_block() -> None:
    entries = [
        {
            "type": "system",
            "subtype": "compact_boundary",
            "content": "Conversation compacted",
        },
        _user("The summary", isCompactSummary=True),
    ]
    block = _only(entries)
    assert (block.kind, block.text) == (Kind.COMPACTED, "The summary")


def test_compact_summary_without_boundary_is_its_own_block() -> None:
    block = _only([_user("The summary", isCompactSummary=True)])
    assert (block.kind, block.text) == (Kind.COMPACTED, "The summary")


def test_local_command_system_entry_is_user_message() -> None:
    entry = {
        "type": "system",
        "subtype": "local_command",
        "content": "<command-name>/cd</command-name><command-args>/tmp</command-args>",
    }
    block = _only([entry])
    assert (block.kind, block.text) == (Kind.USER, "/cd /tmp")


def test_other_system_entry_with_content_is_meta_with_subtype_summary() -> None:
    entry = {"type": "system", "subtype": "info", "content": " note "}
    block = _only([entry])
    assert (block.kind, block.text, block.summary) == (Kind.META, "note", "info")


@pytest.mark.parametrize("content", [None, "", "  "])
def test_system_entry_without_content_produces_nothing(content: str | None) -> None:
    entry: dict[str, Any] = {"type": "system", "subtype": "info"}
    if content is not None:
        entry["content"] = content
    assert parse_entries([entry]) == []


def test_unknown_entry_types_are_ignored() -> None:
    assert parse_entries([{"type": "attachment"}, {"nope": 1}]) == []


# Assistant content and timestamps


def test_assistant_blocks_by_type_and_blank_text_skipped() -> None:
    entries = [
        _text("a1", "  hi  "),
        _text("a2", "   "),
        _thinking("a3"),
        _agent("a4", {"type": "thinking", "thinking": " "}),
    ]
    blocks = parse_entries(entries)
    assert [(b.kind, b.text) for b in blocks] == [
        (Kind.RESULT, "hi"),
        (Kind.THINKING, "hmm"),
    ]


@pytest.mark.parametrize(
    ("stamp", "expected"),
    [
        ("2026-11-06T10:00:00.000Z", datetime(2026, 11, 6, 10, tzinfo=UTC)),
        ("garbage", None),
        (None, None),
        (12345, None),
    ],
)
def test_timestamp_parsing(stamp: Any, expected: datetime | None) -> None:  # noqa: ANN401
    entry = _text("a1", "hi")
    entry["timestamp"] = stamp
    assert _only([entry]).timestamp == expected


# parse_transcript


def _write(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_parse_transcript_skips_bad_and_harness_lines(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "t.jsonl",
        [
            '{"type":"custom-title","customTitle":"x"}',
            _dumps({"type": "attachment", "attachment": {}}),
            '{"type":"user", not json',
            _dumps(_user("hello")),
            "[1, 2, 3]",
            _dumps(_text("a1", "world")),
        ],
    )
    blocks = parse_transcript(path)
    assert [(b.kind, b.text) for b in blocks] == [
        (Kind.USER, "hello"),
        (Kind.RESULT, "world"),
    ]


def test_parse_transcript_reports_progress_ending_at_one(tmp_path: Path) -> None:
    path = _write(tmp_path / "t.jsonl", [_dumps(_user("hi"))] * 3)
    seen: list[float] = []
    parse_transcript(path, on_progress=seen.append)
    assert seen[-1] == 1.0
    assert all(0 < p <= 1.0 for p in seen)


def test_parse_transcript_handles_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    path.write_text("")
    seen: list[float] = []
    assert parse_transcript(path, on_progress=seen.append) == []
    assert seen[-1] == 1.0
