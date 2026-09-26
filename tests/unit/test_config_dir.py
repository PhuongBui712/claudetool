from pathlib import Path

import pytest

from claudetool.sessions import get_project_sessions_dir
from claudetool.templates import claude_config_dir


@pytest.mark.parametrize("value", [None, "", "   "])
def test_claude_config_dir_defaults_to_home_dot_claude(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str | None
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    if value is None:
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    else:
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", value)
    assert claude_config_dir() == tmp_path / ".claude"


def test_claude_config_dir_uses_env_and_expands_tilde(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "~/.claude-work")
    assert claude_config_dir() == tmp_path / ".claude-work"


def test_project_sessions_dir_follows_config_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    assert get_project_sessions_dir("/a/b") == tmp_path / "cfg" / "projects" / "-a-b"
