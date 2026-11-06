"""Session list, content search, and the small modal dialogs of the TUI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from rich.text import Text
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Input, OptionList, Static
from textual.widgets.option_list import Option, OptionDoesNotExist
from textual.worker import get_current_worker

from claudetool._viewer import ViewerScreen, bar, leave
from claudetool.search import search_sessions
from claudetool.sessions import delete_session_files, enrich_session, rename_session

if TYPE_CHECKING:
    from rich.table import Table
    from textual.app import ComposeResult

    from claudetool.search import SearchHit
    from claudetool.sessions import Session

__all__ = ["SessionListScreen", "session_viewer"]

_KB = 1024
_LIST_CSS = """
#head { height: 2; padding: 0 1; border-bottom: solid #444444; }
#filter, #query { border: none; height: 1; padding: 0 1; }
_Picker, _Picker:focus { border: none; height: 1fr; }
#filter { display: none; }
#filter.-active { display: block; }
"""


class _Picker(OptionList):
    """An option list moved with j/k as well as the arrows."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j", "cursor_down", "move", key_display="jk"),
        Binding("k", "cursor_up", "move", show=False),
        Binding("enter", "select", "open", key_display="⏎"),
    ]


class SessionListScreen(Screen[None]):
    """List a project's sessions, newest first, with prompts and cost filled lazily."""

    DEFAULT_CSS = _LIST_CSS

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("slash", "filter", "filter"),
        Binding("ctrl+f", "search", "search"),
        Binding("r", "rename", "rename"),
        Binding("d", "delete", "delete"),
        Binding("escape", "back", "clear filter", show=False),
        Binding("q", "back", "quit"),
    ]

    def __init__(self, sessions: list[Session], cwd: str) -> None:
        """Show `sessions` of the project at `cwd`."""
        super().__init__()
        self._sessions = sessions
        self._project = Path(cwd).name or cwd

    def compose(self) -> ComposeResult:
        """Lay out header, list, filter input, and footer."""
        yield Static(id="head")
        yield _Picker()
        yield Input(placeholder="filter by title or id", id="filter")
        yield Footer()

    def on_mount(self) -> None:
        """Show the fast list now; fill prompts and cost in a worker."""
        self._refill()
        self.query_one(_Picker).focus()
        self.run_worker(self._enrich, thread=True, exit_on_error=False)

    def action_filter(self) -> None:
        """Show the filter input."""
        filter_input = self.query_one("#filter", Input)
        filter_input.add_class("-active")
        filter_input.focus()

    def action_search(self) -> None:
        """Open content search across this project's sessions."""
        self.app.push_screen(SearchScreen(self._sessions, self._project))

    def action_back(self) -> None:
        """Clear an active filter, else quit."""
        filter_input = self.query_one("#filter", Input)
        if filter_input.has_class("-active"):
            filter_input.value = ""
            filter_input.remove_class("-active")
            self.query_one(_Picker).focus()
            self._refill()
        else:
            leave(self)

    def action_rename(self) -> None:
        """Ask for a new title for the highlighted session."""
        session = self._highlighted()
        if session is None:
            return

        def renamed(title: str | None) -> None:
            if title:
                rename_session(session, title)
                session["custom_title"] = session["label"] = title
                self._refill()

        prompt = f"Rename {session['session_id'][:8]}"
        self.app.push_screen(
            RenameScreen(prompt, session["custom_title"] or ""), renamed
        )

    def action_delete(self) -> None:
        """Delete the highlighted session after a y/N confirmation."""
        session = self._highlighted()
        if session is None:
            return

        def confirmed(yes: bool | None) -> None:  # noqa: FBT001
            if yes:
                delete_session_files(session["file"])
                self._sessions.remove(session)
                self._refill()

        question = f"Delete {session['label']!r} ({session['session_id'][:8]})?"
        self.app.push_screen(ConfirmScreen(question), confirmed)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Narrow the list as the filter is typed."""
        event.stop()
        self._refill()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Keep the filter and return to the list."""
        event.stop()
        if not event.value:
            event.input.remove_class("-active")
        self.query_one(_Picker).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Open the selected session in the viewer."""
        session = self._by_id(event.option.id)
        if session is not None:
            self.app.push_screen(session_viewer(session, self._project))

    def _highlighted(self) -> Session | None:
        option = self.query_one(_Picker).highlighted_option
        return self._by_id(option.id) if option else None

    def _by_id(self, session_id: str | None) -> Session | None:
        return next((s for s in self._sessions if s["session_id"] == session_id), None)

    def _refill(self) -> None:
        query = self.query_one("#filter", Input).value.strip().lower()
        shown = [
            s
            for s in self._sessions
            if query in s["label"].lower() or query in s["session_id"].lower()
        ]
        picker = self.query_one(_Picker)
        highlighted = picker.highlighted or 0
        picker.set_options(Option(_row(s), id=s["session_id"]) for s in shown)
        if shown:
            picker.highlighted = min(highlighted, len(shown) - 1)
        size_mb = sum(s["file_size_kb"] for s in self._sessions) / _KB
        count = f"{len(shown)}/{len(self._sessions)}" if query else len(self._sessions)
        title = Text.assemble(("claudetool", "bold #d97757"), f" · {self._project}")
        right = Text(f"{count} sessions · {size_mb:,.0f} MB", style="dim")
        self.query_one("#head", Static).update(bar(title, right))

    def _enrich(self) -> None:
        worker = get_current_worker()
        for session in list(self._sessions):
            if worker.is_cancelled:
                return
            enrich_session(session)
            self.app.call_from_thread(self._update_row, session)

    def _update_row(self, session: Session) -> None:
        try:
            self.query_one(_Picker).replace_option_prompt(
                session["session_id"], _row(session)
            )
        except OptionDoesNotExist:
            return


class SearchScreen(Screen[None]):
    """Search the content of every session in the project."""

    DEFAULT_CSS = _LIST_CSS

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("slash", "edit", "edit query"),
        Binding("escape", "back", "back"),
        Binding("q", "back", "back", show=False),
    ]

    def __init__(self, sessions: list[Session], project: str) -> None:
        """Search over `sessions` of `project`."""
        super().__init__()
        self._project = project
        self._sessions = {s["file"]: s for s in sessions}
        self._hits: list[SearchHit] = []
        self._query = ""

    def compose(self) -> ComposeResult:
        """Lay out header, query input, results, and footer."""
        yield Static(id="head")
        yield Input(placeholder="search all sessions, then ⏎", id="query")
        yield _Picker()
        yield Footer()

    def on_mount(self) -> None:
        """Wait for a query."""
        self._render_head("")

    def action_edit(self) -> None:
        """Focus the query input."""
        self.query_one("#query", Input).focus()

    def action_back(self) -> None:
        """Leave the search; its worker is cancelled with the screen."""
        self.app.pop_screen()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Start a new search, cancelling the previous one."""
        event.stop()
        self._query = event.value.strip()
        self._hits = []
        self.query_one(_Picker).clear_options()
        self.query_one(_Picker).focus()
        if self._query:
            self._render_head("searching…")
            self.run_worker(
                self._search, thread=True, exclusive=True, exit_on_error=False
            )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Open the hit's session focused on the matching block."""
        hit = self._hits[event.option_index]
        session = self._sessions.get(hit.session_file)
        if session is not None:
            viewer = session_viewer(session, self._project, focus_uuid=hit.uuid)
            self.app.push_screen(viewer)

    def _search(self) -> None:
        worker = get_current_worker()
        query = self._query
        hits = search_sessions(
            list(self._sessions), query, cancelled=lambda: worker.is_cancelled
        )
        for hit in hits:
            if worker.is_cancelled:
                return
            self.app.call_from_thread(self._add_hit, hit, query)
        if not worker.is_cancelled:
            self.app.call_from_thread(self._render_head, "done")

    def _add_hit(self, hit: SearchHit, query: str) -> None:
        self._hits.append(hit)
        session = self._sessions.get(hit.session_file)
        label = session["label"] if session else hit.session_file.stem[:8]
        when = _ago(hit.timestamp) if hit.timestamp else "?"
        snippet = Text(" ".join(hit.snippet.split()))
        snippet.highlight_words([query], "bold reverse", case_sensitive=False)
        line = Text.assemble(
            (label[:30], "bold"), f" · {hit.kind} · {when} · ", snippet
        )
        picker = self.query_one(_Picker)
        picker.add_option(bar(line, ""))
        if picker.highlighted is None:
            picker.highlighted = 0
        self._render_head("searching…")

    def _render_head(self, state: str) -> None:
        count = f"{len(self._hits)} hits · {state}" if self._query else ""
        title = Text("search sessions", style="bold")
        self.query_one("#head", Static).update(bar(title, Text(count, style="dim")))


class RenameScreen(ModalScreen[str | None]):
    """Ask for a new title."""

    DEFAULT_CSS = """
    RenameScreen { align: center middle; }
    RenameScreen > Vertical { width: 70%; height: auto; border: round #d97757; }
    """

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "cancel")]

    def __init__(self, prompt: str, current: str) -> None:
        """Ask `prompt`, prefilled with `current`."""
        super().__init__()
        self._prompt = prompt
        self._current = current

    def compose(self) -> ComposeResult:
        """Show the prompt and the input."""
        with Vertical():
            yield Static(self._prompt)
            yield Input(self._current, placeholder="new title")
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Return the typed title, or nothing when blank or unchanged."""
        title = event.value.strip()
        self.dismiss(title if title and title != self._current else None)

    def action_cancel(self) -> None:
        """Return nothing."""
        self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    """Ask a y/N question; anything but `y` answers no."""

    DEFAULT_CSS = """
    ConfirmScreen { align: center middle; }
    ConfirmScreen > Static {
        width: auto; max-width: 80%; padding: 1 2; border: round red;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("y", "answer(True)", "yes"),
        Binding("n,escape,enter,q", "answer(False)", "no"),
    ]

    def __init__(self, question: str) -> None:
        """Ask `question`."""
        super().__init__()
        self._question = question

    def compose(self) -> ComposeResult:
        """Show the question."""
        yield Static(f"{self._question}  [y/N]")
        yield Footer()

    def action_answer(self, yes: bool) -> None:  # noqa: FBT001
        """Return the answer."""
        self.dismiss(yes)


def session_viewer(
    session: Session, project: str, *, focus_uuid: str | None = None
) -> ViewerScreen:
    """Build a viewer for `session`, optionally focused on the entry `focus_uuid`."""
    return ViewerScreen(
        session["file"],
        crumbs=[project, session["session_id"][:8]],
        root_file=session["file"],
        focus_uuid=focus_uuid,
        cost=session["total_cost"],
    )


def _row(session: Session) -> Table:
    """Two lines: title and age/size/cost, then id, prompts, subagents, branch."""
    prompts = session["prompt_count"]
    cost = session["total_cost"]
    title = Text(session["label"], style="bold" if session["custom_title"] else "")
    stats = f"{_ago(session['last_active']):>7}  {_size(session['file_size_kb']):>6}"
    details = [
        session["session_id"][:8],
        f"{'…' if prompts is None else prompts} prompts",
        f"{session['subagent_count']} subagents",
    ]
    if session["git_branch"]:
        details.append(session["git_branch"])
    grid = bar(title, Text(f"{stats}  {'…' if cost is None else f'${cost:,.2f}':>8}"))
    grid.add_row(Text(" · ".join(details), style="dim"), "")
    return grid


def _ago(when: datetime) -> str:
    seconds = (datetime.now(when.tzinfo) - when).total_seconds()
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{int(seconds // size)}{unit} ago"
    return "just now"


def _size(kb: float) -> str:
    return f"{kb / _KB:,.0f} MB" if kb >= _KB else f"{kb:,.0f} KB"
