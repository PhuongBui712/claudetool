"""Transcript viewer: a lazily rendered, block-wise navigable view of one transcript.

Sessions can hold thousands of blocks and megabyte tool outputs, so the view never
mounts a widget per block nor measures the whole transcript. It keeps a viewport
as (top row, line offset), renders only the blocks it draws, and caches their
lines per width and view mode.
"""

from __future__ import annotations

import json
import re
from bisect import bisect_left
from collections import OrderedDict
from typing import TYPE_CHECKING, ClassVar

from rich.cells import chop_cells
from rich.markdown import Markdown
from rich.segment import Segment
from rich.style import Style
from rich.table import Table
from rich.text import Text
from textual.binding import Binding, BindingType
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Footer, Input, OptionList, Static
from textual.widgets.option_list import Option
from textual.worker import get_current_worker

from claudetool.sessions import list_subagents, subagent_file
from claudetool.stats import session_cost
from claudetool.transcript import Block, Kind, parse_transcript

if TYPE_CHECKING:
    from pathlib import Path

    from rich.console import Console, RenderableType
    from textual import events
    from textual.app import ComposeResult

    from claudetool.sessions import Subagent

__all__ = ["ViewerScreen", "bar", "leave"]

_GUTTER = 2
_CACHE_SIZE = 512
_WHEEL_LINES = 3
_HIDDEN_WHEN_COLLAPSED = (Kind.THINKING, Kind.META)
_AGENT_TOOLS = ("Agent", "Task")
_ACCENT = "#d97757"
_DIM = Style(dim=True)
_ERROR = Style(color="red")
_FOCUS_BG = Style(bgcolor="#2a2d37")
_USER_BG = Style(bgcolor="#1f2633")
_USER_FOCUS_BG = Style(bgcolor="#2c3850")
_MATCH = Style(bgcolor="#8a6d00", color="white", bold=True)
_CONTROL_RE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|[\x00-\x08\x0b-\x1f\x7f]"
)


def bar(left: RenderableType, right: RenderableType) -> Table:
    """Lay out a one-line header: `left` flush left, `right` flush right."""
    grid = Table.grid(expand=True)
    grid.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
    grid.add_column(justify="right", no_wrap=True)
    grid.add_row(left, right)
    return grid


def leave(screen: Screen[None]) -> None:
    """Pop `screen`, or quit when it is the first screen the app pushed."""
    if screen.app.screen_stack[1:2] == [screen]:
        screen.app.exit()
    else:
        screen.app.pop_screen()


class TranscriptView(Widget, can_focus=True):
    """Draw the blocks of one transcript and move a focus between them."""

    DEFAULT_CSS = "TranscriptView { height: 1fr; }"

    class Changed(Message):
        """The focus, viewport, or view mode changed."""

    def __init__(self) -> None:
        """Start empty; `load` supplies the blocks."""
        super().__init__()
        self.blocks: list[Block] = []
        self.expanded = False
        self.needle = ""
        self._rows: list[int] = []
        self._focus = 0
        self._top = 0
        self._offset = 0
        self._cache: OrderedDict[tuple[int, int, bool], list[Strip]] = OrderedDict()
        self._haystacks: dict[int, str] = {}
        self._layout_key: tuple[int, ...] = ()
        self._layout_rows: list[tuple[int, int]] = []

    @property
    def focused(self) -> Block | None:
        """The focused block, if any."""
        return self.blocks[self._rows[self._focus]] if self._rows else None

    @property
    def position(self) -> tuple[int, int]:
        """The focused block's 1-based place among the shown blocks, and their count."""
        return (self._focus + 1 if self._rows else 0), len(self._rows)

    def load(self, blocks: list[Block], *, focus_uuid: str | None = None) -> None:
        """Show `blocks`, focused on the one at `focus_uuid` or else the last."""
        self.blocks = blocks
        target = next((i for i, b in enumerate(blocks) if b.uuid == focus_uuid), None)
        if target is not None and blocks[target].kind in _HIDDEN_WHEN_COLLAPSED:
            self.expanded = True
        self._rebuild()
        if target is None:
            self.end()
        else:
            self._focus = self._row_of(target)
            self._top, self._offset = self._focus, 0
            self._settle()

    def move(self, delta: int) -> None:
        """Move the focus by `delta` blocks and scroll it into view."""
        if not self._rows:
            return
        self._focus = max(0, min(len(self._rows) - 1, self._focus + delta))
        self._reveal(self._focus)
        self._settle()

    def home(self) -> None:
        """Focus the first block."""
        self._focus = self._top = self._offset = 0
        self._settle()

    def end(self) -> None:
        """Focus the last block, bottom-aligned."""
        if self._rows:
            self._focus = len(self._rows) - 1
            self._bottom_align(self._focus)
        self._settle()

    def page(self, direction: int) -> None:
        """Scroll one screen down (`1`) or up (`-1`)."""
        self.scroll_lines(direction * max(1, self.size.height - 1))

    def scroll_lines(self, count: int) -> None:
        """Scroll the viewport by `count` lines, keeping the focus on screen."""
        if not self._rows:
            return
        self._offset += count
        while self._top < len(self._rows) - 1 and self._offset >= len(
            self._strips(self._top)
        ):
            self._offset -= len(self._strips(self._top))
            self._top += 1
        while self._offset < 0 and self._top > 0:
            self._top -= 1
            self._offset += len(self._strips(self._top))
        self._offset = max(0, self._offset)
        self._clamp()
        shown = [row for row, _ in self._layout()]
        if shown and not shown[0] <= self._focus <= shown[-1]:
            self._focus = shown[0] if self._focus < shown[0] else shown[-1]
        self._settle()

    def toggle(self) -> None:
        """Switch between collapsed and expanded view, keeping the focus in place."""
        anchor = self._rows[self._focus] if self._rows else 0
        layout = self._layout()
        screen_y = layout.index((self._focus, 0)) if (self._focus, 0) in layout else 0
        self.expanded = not self.expanded
        self._rebuild()
        if self._rows:
            self._focus = self._row_of(anchor)
            self._top, self._offset = self._focus, 0
            self.scroll_lines(-screen_y)
        self._settle()

    def find(self, query: str, *, backward: bool = False) -> bool:
        """Focus the next (or previous) block containing `query`, case-insensitive.

        A match in a kind the collapsed view hides switches to the expanded view.

        Returns:
            Whether a matching block exists.
        """
        self.needle = query.lower()
        if not self.needle or not self.blocks:
            self.refresh()
            return False
        count = len(self.blocks)
        start = self._rows[self._focus] if self._rows else 0
        for step in range(1, count + 1):
            index = (start - step if backward else start + step) % count
            if self.needle in self._haystack(index):
                break
        else:
            self.refresh()
            return False
        if not self.expanded and self.blocks[index].kind in _HIDDEN_WHEN_COLLAPSED:
            self.expanded = True
            self._rebuild()
        self._focus = self._row_of(index)
        self._reveal(self._focus)
        self._settle()
        return True

    def render_line(self, y: int) -> Strip:
        """Draw screen line `y`, adding focus and match highlights at draw time."""
        width = self.size.width
        layout = self._layout()
        if y >= len(layout):
            return Strip.blank(width, self.rich_style)
        row, line = layout[y]
        strip = self._strips(row)[line]
        if self.needle:
            strip = _highlight(strip, self.needle)
        is_user = self.blocks[self._rows[row]].kind is Kind.USER
        if row == self._focus:
            base = _USER_FOCUS_BG if is_user else _FOCUS_BG
        else:
            base = _USER_BG if is_user else Style()
        return strip.adjust_cell_length(width).apply_style(self.rich_style + base)

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        """Scroll down by a few lines, not by block."""
        event.stop()
        self.scroll_lines(_WHEEL_LINES)

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        """Scroll up by a few lines, not by block."""
        event.stop()
        self.scroll_lines(-_WHEEL_LINES)

    def on_resize(self) -> None:
        """Re-clamp the viewport to the new size."""
        self._clamp()
        self._settle()

    def _settle(self) -> None:
        self.refresh()
        self.post_message(self.Changed())

    def _rebuild(self) -> None:
        self._rows = [
            i
            for i, block in enumerate(self.blocks)
            if self.expanded or block.kind not in _HIDDEN_WHEN_COLLAPSED
        ]
        self._focus = min(self._focus, max(0, len(self._rows) - 1))
        self._top, self._offset = 0, 0

    def _row_of(self, index: int) -> int:
        """The shown row of block `index`, or the nearest one after it."""
        return min(bisect_left(self._rows, index), len(self._rows) - 1)

    def _haystack(self, index: int) -> str:
        if index not in self._haystacks:
            block = self.blocks[index]
            joined = f"{block.tool_name}\n{block.summary}\n{block.text}\n{block.output}"
            self._haystacks[index] = joined.lower()
        return self._haystacks[index]

    def _strips(self, row: int) -> list[Strip]:
        key = (self._rows[row], self.size.width, self.expanded)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        strips = _render_block(
            self.blocks[key[0]],
            key[1],
            expanded=self.expanded,
            console=self.app.console,
        )
        self._cache[key] = strips
        if len(self._cache) > _CACHE_SIZE:
            self._cache.popitem(last=False)
        return strips

    def _layout(self) -> list[tuple[int, int]]:
        """Map each screen line to (row, line within that row's block)."""
        height = self.size.height
        key = (self._top, self._offset, self.size.width, height, len(self._rows))
        if key == self._layout_key:
            return self._layout_rows
        rows: list[tuple[int, int]] = []
        row, line = self._top, self._offset
        while len(rows) < height and row < len(self._rows):
            count = len(self._strips(row))
            rows.extend(
                (row, i) for i in range(line, min(count, line + height - len(rows)))
            )
            row, line = row + 1, 0
        self._layout_key, self._layout_rows = key, rows
        return rows

    def _reveal(self, row: int) -> None:
        if row < self._top or (row == self._top and self._offset):
            self._top, self._offset = row, 0
            return
        height = self.size.height
        if row - self._top >= height:
            self._bottom_align(row)
            return
        lines = len(self._strips(self._top)) - self._offset
        lines += sum(len(self._strips(r)) for r in range(self._top + 1, row + 1))
        if lines > height:
            self._bottom_align(row)

    def _bottom_align(self, row: int) -> None:
        """Scroll so block `row` ends at the bottom, or starts at the top if taller."""
        remaining = self.size.height - len(self._strips(row))
        self._top, self._offset = row, 0
        while remaining > 0 and self._top > 0:
            self._top -= 1
            height = len(self._strips(self._top))
            if height >= remaining:
                self._offset = height - remaining
                return
            remaining -= height
        if remaining > 0:
            self._top, self._offset = 0, 0

    def _clamp(self) -> None:
        """Avoid blank space below the last block when there is content above."""
        if not self._rows:
            return
        self._offset = min(self._offset, len(self._strips(self._top)) - 1)
        if len(self._layout()) < self.size.height:
            self._bottom_align(len(self._rows) - 1)


class ViewerScreen(Screen[None]):
    """Show one transcript; Enter on an `Agent` call opens its subagent."""

    DEFAULT_CSS = """
    ViewerScreen #head { height: 2; padding: 0 1; border-bottom: solid #444444; }
    ViewerScreen #find { display: none; border: none; height: 1; padding: 0 1; }
    ViewerScreen #find.-active { display: block; }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j,down", "move(1)", "block", key_display="jk"),
        Binding("k,up", "move(-1)", "block", show=False),
        Binding("ctrl+o", "toggle_view", "expand/collapse"),
        Binding("slash", "find", "search"),
        Binding("n", "next_match(False)", "next"),
        Binding("N", "next_match(True)", "prev"),
        Binding("enter", "open_agent", "open subagent"),
        Binding("a", "subagents", "subagents"),
        Binding("g,home", "home", "top", show=False),
        Binding("G,end", "end", "bottom", show=False),
        Binding("pageup", "page(-1)", "page up", show=False),
        Binding("pagedown,space", "page(1)", "page down", show=False),
        Binding("escape,q", "back", "back"),
    ]

    def __init__(
        self,
        file: Path,
        *,
        crumbs: list[str],
        root_file: Path,
        focus_uuid: str | None = None,
        cost: float | None = None,
    ) -> None:
        """Prepare a viewer; the transcript is read in a worker once mounted.

        Args:
            file: The transcript to show.
            crumbs: The breadcrumb trail naming what is open.
            root_file: The session transcript owning `file` (itself for a session).
            focus_uuid: The entry to focus instead of the last block.
            cost: The known cost of what is open; computed in a worker when `None`.
        """
        super().__init__()
        self._file = file
        self._crumbs = crumbs
        self._root_file = root_file
        self._focus_uuid = focus_uuid
        self._cost = cost
        self._progress = 0.0
        self._loaded = False
        self._subagents: list[Subagent] = []

    def compose(self) -> ComposeResult:
        """Lay out header, transcript, search input, and footer."""
        yield Static(id="head")
        yield TranscriptView()
        yield Input(placeholder="search this transcript", id="find")
        yield Footer()

    def on_mount(self) -> None:
        """Start reading the transcript and its cost off the UI thread."""
        self._render_head()
        self.query_one(TranscriptView).focus()
        self.run_worker(self._load, thread=True, exit_on_error=False)
        if self._cost is None:
            self.run_worker(self._load_cost, thread=True, exit_on_error=False)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Hide keys that do nothing in the current state."""
        del parameters
        view = self.query_one(TranscriptView)
        if action == "next_match":
            return bool(view.needle)
        if action == "open_agent":
            return _opens_agent(view.focused)
        if action == "subagents":
            return bool(self._subagents)
        return True

    def action_move(self, delta: int) -> None:
        """Move the focus by blocks."""
        self.query_one(TranscriptView).move(delta)

    def action_toggle_view(self) -> None:
        """Toggle collapsed/expanded view."""
        self.query_one(TranscriptView).toggle()

    def action_home(self) -> None:
        """Focus the first block."""
        self.query_one(TranscriptView).home()

    def action_end(self) -> None:
        """Focus the last block."""
        self.query_one(TranscriptView).end()

    def action_page(self, direction: int) -> None:
        """Scroll by a screen."""
        self.query_one(TranscriptView).page(direction)

    def action_find(self) -> None:
        """Show the search input."""
        find = self.query_one("#find", Input)
        find.add_class("-active")
        find.focus()

    def action_next_match(self, backward: bool) -> None:  # noqa: FBT001
        """Jump to the next or previous match of the last search."""
        view = self.query_one(TranscriptView)
        if not view.find(view.needle, backward=backward):
            self.notify(f"no match for {view.needle!r}", severity="warning")

    def action_open_agent(self) -> None:
        """Open the subagent the focused `Agent` call launched."""
        block = self.query_one(TranscriptView).focused
        if block is None or not _opens_agent(block):
            return
        self._open_subagent(block.agent_id)

    def action_subagents(self) -> None:
        """Pick one of the session's subagents to open."""

        def opened(picked: Subagent | None) -> None:
            if picked is not None:
                self._open_subagent(picked.agent_id, picked.file)

        self.app.push_screen(SubagentPicker(self._subagents), opened)

    def action_back(self) -> None:
        """Close the search input, else leave this viewer."""
        find = self.query_one("#find", Input)
        if find.has_class("-active"):
            find.remove_class("-active")
            self.query_one(TranscriptView).focus()
        else:
            leave(self)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Run the search typed into the input."""
        event.stop()
        view = self.query_one(TranscriptView)
        event.input.remove_class("-active")
        view.focus()
        if event.value and not view.find(event.value):
            self.notify(f"no match for {event.value!r}", severity="warning")

    def on_transcript_view_changed(self) -> None:
        """Keep the header and the footer's keys current."""
        self._render_head()
        self.refresh_bindings()

    def _open_subagent(self, agent_id: str, file: Path | None = None) -> None:
        file = file or subagent_file(self._root_file, agent_id)
        if file is None:
            self.notify("subagent transcript not found", severity="warning")
            return
        crumbs = [*self._crumbs, f"agent-{agent_id[:8]}"]
        self.app.push_screen(
            ViewerScreen(file, crumbs=crumbs, root_file=self._root_file)
        )

    def _load(self) -> None:
        worker = get_current_worker()

        def progress(fraction: float) -> None:
            if not worker.is_cancelled:
                self.app.call_from_thread(self._set_progress, fraction)

        try:
            blocks = parse_transcript(self._file, on_progress=progress)
            subagents = list_subagents(self._root_file)
        except OSError as e:
            self.app.call_from_thread(self.notify, str(e), severity="error")
            return
        if not worker.is_cancelled:
            self.app.call_from_thread(self._show, blocks, subagents)

    def _load_cost(self) -> None:
        is_subagent = self._file != self._root_file
        cost = session_cost(self._file, include_subagents=not is_subagent)
        if not get_current_worker().is_cancelled:
            self.app.call_from_thread(self._set_cost, cost)

    def _set_progress(self, fraction: float) -> None:
        self._progress = fraction
        self._render_head()

    def _set_cost(self, cost: float) -> None:
        self._cost = cost
        self._render_head()

    def _show(self, blocks: list[Block], subagents: list[Subagent]) -> None:
        self._loaded = True
        self._subagents = subagents
        self.query_one(TranscriptView).load(blocks, focus_uuid=self._focus_uuid)

    def _render_head(self) -> None:
        view = self.query_one(TranscriptView)
        crumbs = Text(" › ".join(self._crumbs), style="bold")  # noqa: RUF001
        if not self._loaded:
            right = Text(f"reading {self._progress:.0%}", style="dim")
        else:
            focus, total = view.position
            mode = (
                "expanded · ^O collapse" if view.expanded else "collapsed · ^O expand"
            )
            right = Text(f"{mode} · block {focus:,}/{total:,}", style="dim")
        if self._cost is not None:
            right.append(f" · ${self._cost:,.2f}", style="yellow")
        self.query_one("#head", Static).update(bar(crumbs, right))


class SubagentPicker(ModalScreen["Subagent | None"]):
    """Choose one subagent of a session."""

    DEFAULT_CSS = """
    SubagentPicker { align: center middle; }
    SubagentPicker OptionList { width: 80%; height: auto; max-height: 80%; }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j", "cursor(1)", "move", key_display="jk"),
        Binding("k", "cursor(-1)", "move", show=False),
        Binding("escape,q", "dismiss_none", "back"),
    ]

    def __init__(self, subagents: list[Subagent]) -> None:
        """List `subagents` for picking."""
        super().__init__()
        self._subagents = subagents

    def compose(self) -> ComposeResult:
        """Show one option per subagent, then the footer."""
        yield OptionList(
            *(
                Option(
                    Text.assemble(
                        s.description or s.agent_id,
                        (f" · {s.agent_type} · {s.model}", "dim"),
                    )
                )
                for s in self._subagents
            )
        )
        yield Footer()

    def action_cursor(self, delta: int) -> None:
        """Move the highlight."""
        options = self.query_one(OptionList)
        if delta > 0:
            options.action_cursor_down()
        else:
            options.action_cursor_up()

    def action_dismiss_none(self) -> None:
        """Close without picking."""
        self.dismiss(None)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Pick the selected subagent."""
        self.dismiss(self._subagents[event.option_index])


def _opens_agent(block: Block | None) -> bool:
    return bool(block and block.tool_name in _AGENT_TOOLS and block.agent_id)


def _highlight(strip: Strip, query: str) -> Strip:
    text = strip.text.lower()
    cuts: list[int] = []
    start = text.find(query)
    while start != -1:
        cuts += [start, start + len(query)]
        start = text.find(query, start + len(query))
    if not cuts:
        return strip
    cells = [strip.index_to_cell_position(i) for i in cuts]
    pieces = strip.divide([*cells, strip.cell_length])
    return Strip.join(
        Strip(Segment.apply_style(piece, post_style=_MATCH)) if i % 2 else piece
        for i, piece in enumerate(pieces)
    )


def _render_block(
    block: Block, width: int, *, expanded: bool, console: Console
) -> list[Strip]:
    """Render one block to lines, ending with a blank separator line."""
    body = max(width - _GUTTER, 10)
    kind = block.kind
    if kind is Kind.USER:
        lines = _gutter(_plain(block.text, body), "❯ ", Style(bold=True))  # noqa: RUF001
    elif kind is Kind.AGENT:
        markdown = _markdown(block.text, body, console)
        lines = [s.apply_style(_DIM) for s in _gutter(markdown, "● ", _DIM)]
    elif kind is Kind.RESULT:
        markdown = _markdown(block.text, body, console)
        lines = _gutter(markdown, "▌ ", Style(color=_ACCENT), rest="▌ ")
    elif kind is Kind.TOOL:
        lines = _tool(block, width, body, expanded=expanded, console=console)
    elif kind is Kind.THINKING:
        lines = _gutter(
            _plain(block.text, body, Style(dim=True, italic=True)), "✻ ", _DIM
        )
    elif kind is Kind.META:
        label = f"meta · {block.summary}" if block.summary else "meta"
        lines = [Strip([Segment(f"· {label}", _DIM)])]
        lines += _gutter(_plain(block.text, body, _DIM), "  ", _DIM)
    elif kind is Kind.INTERRUPTED:
        lines = [Strip([Segment("⏹ interrupted", _DIM)])]
    else:
        label = " compacted "
        side = max(2, (width - len(label)) // 2)
        lines = [Strip([Segment(f"{'─' * side}{label}{'─' * side}", _DIM)])]
        if expanded:
            lines += _gutter(_plain(block.text, body, _DIM), "  ", _DIM)
    return [*lines, Strip([])]


def _tool(
    block: Block, width: int, body: int, *, expanded: bool, console: Console
) -> list[Strip]:
    head = Text.assemble(
        ("● ", _ERROR if block.is_error else Style(color="green")),
        (block.tool_name, "bold"),
        f"({block.summary})" if block.summary else "",
    )
    if block.tool_name in _AGENT_TOOLS:
        agent_type = _input_field(block.text, "subagent_type")
        if agent_type:
            head.append(f" · {agent_type}", style="dim")
        if block.agent_id:
            head.append("  ⏎", style="dim")
    head.no_wrap = True
    head.overflow = "ellipsis"
    options = console.options.update_width(width)
    lines = [Strip(line) for line in console.render_lines(head, options, pad=False)]
    if expanded:
        lines += _gutter(_plain(block.text, body, _DIM), "  ", _DIM)
        output = _plain(
            block.output or "(no result)", body, _ERROR if block.is_error else Style()
        )
        return lines + _gutter(output, "⎿ ", _DIM)
    if block.is_error:
        first = _clean(block.output).strip().split("\n", 1)[0]
        status, style = f"error: {first}", _ERROR
    elif block.output:
        status, style = f"{block.output.count(chr(10)) + 1:,} lines", _DIM
    else:
        status, style = "(no result)", _DIM
    return [
        *lines,
        Strip([Segment("  ⎿ ", _DIM), Segment(status, style)]).crop(0, width),
    ]


def _input_field(tool_input: str, key: str) -> str:
    try:
        value = json.loads(tool_input).get(key, "")
    except (ValueError, AttributeError):
        return ""
    return value if isinstance(value, str) else ""


def _gutter(
    strips: list[Strip], first: str, style: Style, *, rest: str = "  "
) -> list[Strip]:
    """Prefix the first line with `first` and the others with `rest`."""
    return [
        Strip([Segment(rest if i else first, style), *strip])
        for i, strip in enumerate(strips)
    ]


def _plain(text: str, width: int, style: Style | None = None) -> list[Strip]:
    # Hand-wrapped rather than through Rich: tool outputs reach megabytes.
    return [
        Strip([Segment(chunk, style)])
        for line in _clean(text).split("\n")
        for chunk in chop_cells(line, width) or [""]
    ]


def _markdown(text: str, width: int, console: Console) -> list[Strip]:
    options = console.options.update_width(width)
    rendered = console.render_lines(Markdown(_clean(text)), options, pad=False)
    return [Strip(line) for line in rendered]


def _clean(text: str) -> str:
    """Drop terminal control sequences so tool output cannot repaint the screen."""
    return _CONTROL_RE.sub("", text).expandtabs(4)
