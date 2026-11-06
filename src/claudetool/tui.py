"""Interactive terminal UI: browse, search, rename, delete, and read sessions."""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from textual.app import App
from textual.binding import Binding, BindingType

from claudetool._screens import SessionListScreen, session_viewer

if TYPE_CHECKING:
    from textual.screen import Screen

    from claudetool.sessions import Session

__all__ = ["run_interactive", "run_viewer"]

_INTERRUPTED = 130


class _ClaudeTool(App[None]):
    """Host one first screen; Ctrl+C and termination signals quit from anywhere."""

    ENABLE_COMMAND_PALETTE = False
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+c", "interrupt", "quit", show=False, priority=True),
    ]

    def __init__(self, first: Screen[None]) -> None:
        super().__init__()
        self._first = first

    def on_mount(self) -> None:
        """Show the first screen and quit cleanly on SIGTERM/SIGHUP."""
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGTERM, signal.SIGHUP):
            loop.add_signal_handler(signum, self.exit, None, 128 + signum)
        self.push_screen(self._first)

    def action_interrupt(self) -> None:
        """Quit with the conventional Ctrl+C exit status."""
        self.exit(return_code=_INTERRUPTED)


def run_interactive(sessions: list[Session], cwd: str) -> None:
    """Browse the sessions of the project at `cwd` until the user quits."""
    _run(SessionListScreen(sessions, cwd))


def run_viewer(session: Session, cwd: str) -> None:
    """Open `session` of the project at `cwd` in the viewer; Esc or q exits."""
    _run(session_viewer(session, Path(cwd).name or cwd))


def _run(first: Screen[None]) -> None:
    app = _ClaudeTool(first)
    app.run()
    if app.return_code:
        sys.exit(app.return_code)
