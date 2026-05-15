"""
Interactive TUI — full-screen keyboard-driven session browser.

Uses only Python stdlib (tty, termios, sys, os, select).
Falls back to print_sessions() when stdout is not a TTY.
"""

import os
import sys
import tty
import termios
import select

from claudetool.rendering import (
    BOLD,
    RED,
    GREEN,
    YELLOW,
    CYAN,
    DIM,
    RESET,
    ORANGE,
    AMBER,
    print_sessions,
    render_session_preview,
    open_pager,
    _fmt_cost,
)
from claudetool.sessions import (
    parse_messages,
    delete_sessions,
    rename_session,
)


# ─────────────────────────────────────────────
# Low-level terminal helpers
# ─────────────────────────────────────────────


def _getch() -> str:
    """Read a single keypress (or escape sequence) from stdin."""
    ch = sys.stdin.read(1)
    if ch == "\x1b":
        r, _, _ = select.select([sys.stdin], [], [], 0.05)
        if r:
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                return "\x1b[" + ch3
            return "\x1b" + ch2
    return ch


def _read_line(prompt: str, prefill: str = "") -> str:
    """
    Read a line of input inline (raw mode, echoing characters manually).
    Returns the entered string, or "" if the user pressed Escape.
    """
    buf = list(prefill)
    sys.stdout.write(prompt + prefill)
    sys.stdout.flush()

    old = termios.tcgetattr(sys.stdin)
    try:
        tty.setraw(sys.stdin.fileno())
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                return "".join(buf)
            elif ch == "\x1b":
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                return ""
            elif ch in ("\x7f", "\x08"):
                if buf:
                    buf.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            elif ch >= " ":
                buf.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)


# ─────────────────────────────────────────────
# Row renderer
# ─────────────────────────────────────────────


def _render_row(
    idx: int,
    session: dict,
    selected: bool,
    width: int,
    has_costs: bool,
) -> str:
    sid = session["session_id"][:16]
    date_str = (
        session["created_at"].strftime("%Y-%m-%d %H:%M")
        if session["created_at"]
        else "?"
    )
    label = (session["label"] or "").replace("\n", " ")
    msgs = str(session["message_count"])
    size = f"{session['file_size_kb']}K"

    cost_part = ""
    if has_costs:
        cost = session.get("total_cost")
        cost_part = f"  {YELLOW}{_fmt_cost(cost) or '':>7}{RESET}"

    # Fixed prefix visible length (approx)
    fixed_vis = 4 + 18 + 18 + 9 + 7 + (9 if has_costs else 0) + 2
    avail = max(10, width - fixed_vis)
    plain_label = label[:avail]

    if session["custom_title"]:
        title_col = f"{GREEN}{plain_label}{RESET}"
    else:
        title_col = f"{DIM}{plain_label}{RESET}"

    num = f"{idx + 1:>3}"
    row = (
        f"  {CYAN}{num}{RESET}  "
        f"{CYAN}{sid:<16}{RESET}  "
        f"{DIM}{date_str:<16}{RESET}  "
        f"{DIM}{msgs:>4}msg{RESET}  "
        f"{DIM}{size:>5}{RESET}"
        f"{cost_part}  "
        f"{title_col}"
    )

    if selected:
        row = f"\033[7m{row}\033[27m"

    return row


# ─────────────────────────────────────────────
# TUI class
# ─────────────────────────────────────────────


class _TUI:
    HELP_NORMAL = (
        f" {BOLD}↑/k{RESET} up  {BOLD}↓/j{RESET} down  "
        f"{BOLD}Enter{RESET} preview  "
        f"{BOLD}r{RESET} rename  "
        f"{BOLD}d{RESET} delete  "
        f"{BOLD}/{RESET} filter  "
        f"{BOLD}q{RESET} quit"
    )
    HELP_FILTER = (
        f" {AMBER}Filter:{RESET} type to search  "
        f"{BOLD}Enter{RESET} confirm  "
        f"{BOLD}Esc{RESET} clear"
    )

    def __init__(self, sessions: list[dict], cwd: str) -> None:
        self._all = sessions
        self._cwd = cwd
        self._filtered: list[dict] = list(sessions)
        self._cursor = 0
        self._offset = 0
        self._filter_q = ""
        self._mode = "normal"
        self._status = ""
        self._has_costs = any(s.get("total_cost") is not None for s in sessions)
        self._old_attrs = None

    def _term_size(self) -> tuple[int, int]:
        cols, rows = os.get_terminal_size()
        return cols, rows

    def _vis_rows(self, height: int) -> int:
        return max(1, height - 7)

    def _refresh(self) -> None:
        q = self._filter_q.lower()
        if q:
            self._filtered = [
                s
                for s in self._all
                if q in (s["label"] or "").lower() or q in s["session_id"].lower()
            ]
        else:
            self._filtered = list(self._all)
        if self._filtered:
            self._cursor = min(self._cursor, len(self._filtered) - 1)
            self._cursor = max(0, self._cursor)
        else:
            self._cursor = 0
        self._clamp_offset()

    def _clamp_offset(self) -> None:
        _, height = self._term_size()
        vis = self._vis_rows(height)
        if self._cursor < self._offset:
            self._offset = self._cursor
        elif self._cursor >= self._offset + vis:
            self._offset = self._cursor - vis + 1

    def _render(self) -> None:
        width, height = self._term_size()
        vis = self._vis_rows(height)
        lines: list[str] = []

        lines.append("")
        lines.append(
            f"  {BOLD}{ORANGE}claudetool{RESET}  "
            f"{DIM}─{RESET}  "
            f"{DIM}project:{RESET} {CYAN}{self._cwd}{RESET}"
        )
        filter_info = (
            f"  {AMBER}[filter: {self._filter_q}]{RESET}" if self._filter_q else ""
        )
        lines.append(
            f"  {DIM}{len(self._filtered)}/{len(self._all)} sessions{filter_info}{RESET}"
        )
        lines.append("")

        hdr = f"  {'#':>3}  {'Session ID':<16}  {'Date':<16}  {'Msgs':>7}  {'Size':>5}"
        if self._has_costs:
            hdr += f"  {'Cost':>7}"
        hdr += "  Title"
        lines.append(f"{BOLD}{hdr}{RESET}")
        lines.append(f"  {DIM}{'─' * (width - 4)}{RESET}")

        for i in range(vis):
            ri = self._offset + i
            if ri >= len(self._filtered):
                lines.append("")
                continue
            s = self._filtered[ri]
            sel = ri == self._cursor
            lines.append(_render_row(ri, s, sel, width, self._has_costs))

        lines.append("")
        if self._status:
            lines.append(f"  {self._status}")
            self._status = ""
        elif self._mode == "filter":
            lines.append(f"  {self.HELP_FILTER}  {AMBER}{self._filter_q}▌{RESET}")
        else:
            lines.append(f"  {self.HELP_NORMAL}")
        lines.append("")

        out = "\033[H\033[J" + "\r\n".join(lines)
        sys.stdout.write(out)
        sys.stdout.flush()

    def _action_preview(self) -> None:
        if not self._filtered:
            return
        session = self._filtered[self._cursor]
        messages = parse_messages(session["file"])
        rendered = render_session_preview(session, messages)
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_attrs)
        open_pager(rendered)
        tty.setraw(sys.stdin.fileno())

    def _action_rename(self) -> None:
        if not self._filtered:
            return
        session = self._filtered[self._cursor]
        prefill = session.get("custom_title") or ""

        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_attrs)
        sys.stdout.write("\033[H\033[J")
        sys.stdout.write(
            f"\r\n  Rename session {CYAN}{session['session_id'][:16]}{RESET}\r\n\r\n"
        )
        sys.stdout.flush()

        new_title = _read_line("  New title: ", prefill)

        if new_title and new_title != prefill:
            rename_session(session, new_title)
            self._status = f"{GREEN}✓ Renamed to:{RESET} {new_title}"
        else:
            self._status = f"{DIM}Rename cancelled.{RESET}"

        tty.setraw(sys.stdin.fileno())

    def _action_delete(self) -> None:
        if not self._filtered:
            return
        session = self._filtered[self._cursor]
        label = session.get("custom_title") or session["session_id"][:24]

        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_attrs)
        sys.stdout.write("\033[H\033[J")
        sys.stdout.write(
            f"\r\n  {RED}Delete{RESET} session: {CYAN}{label}{RESET}\r\n"
            f"\r\n  Confirm? [y/N] "
        )
        sys.stdout.flush()

        ans = sys.stdin.readline().strip().lower()
        if ans == "y":
            delete_sessions([session], dry_run=False)
            self._all = [
                s for s in self._all if s["session_id"] != session["session_id"]
            ]
            self._status = f"{GREEN}✓ Deleted:{RESET} {label}"
            self._refresh()
        else:
            self._status = f"{DIM}Delete cancelled.{RESET}"

        tty.setraw(sys.stdin.fileno())

    def _handle_normal(self, ch: str) -> bool:
        if ch in ("q", "Q", "\x03"):
            return True
        elif ch in ("\x1b[A", "k", "K"):
            if self._cursor > 0:
                self._cursor -= 1
                self._clamp_offset()
        elif ch in ("\x1b[B", "j", "J"):
            if self._cursor < len(self._filtered) - 1:
                self._cursor += 1
                self._clamp_offset()
        elif ch in ("\r", "\n"):
            self._action_preview()
        elif ch in ("r", "R"):
            self._action_rename()
        elif ch in ("d", "D"):
            self._action_delete()
        elif ch == "/":
            self._mode = "filter"
        elif ch == "\x1b":
            self._filter_q = ""
            self._refresh()
        return False

    def _handle_filter(self, ch: str) -> None:
        if ch in ("\r", "\n", "\x1b"):
            self._mode = "normal"
            if ch == "\x1b":
                self._filter_q = ""
            self._refresh()
        elif ch in ("\x7f", "\x08"):
            self._filter_q = self._filter_q[:-1]
            self._refresh()
        elif len(ch) == 1 and ch >= " ":
            self._filter_q += ch
            self._cursor = 0
            self._offset = 0
            self._refresh()

    def run(self) -> None:
        self._old_attrs = termios.tcgetattr(sys.stdin)
        try:
            sys.stdout.write("\033[?25l\033[H\033[J")
            sys.stdout.flush()
            tty.setraw(sys.stdin.fileno())
            self._refresh()
            while True:
                self._render()
                ch = _getch()
                if self._mode == "filter":
                    self._handle_filter(ch)
                else:
                    if self._handle_normal(ch):
                        break
        except Exception:
            pass
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_attrs)
            sys.stdout.write("\033[?25h\033[H\033[J")
            sys.stdout.flush()


# ─────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────


def run_interactive(sessions: list[dict], cwd: str) -> None:
    """
    Launch the interactive TUI if stdout is a TTY.
    Falls back to print_sessions() otherwise.
    """
    if not sys.stdout.isatty() or not sys.stdin.isatty():
        print_sessions(sessions)
        return
    if not sessions:
        print_sessions(sessions)
        return
    _TUI(sessions, cwd).run()
