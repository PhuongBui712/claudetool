"""
Terminal rendering — ANSI colours, text helpers, session display.

Everything related to "how things look in the terminal" lives here.
This module receives data and formats it; it does not fetch or parse anything.
"""

import os
import re
import shutil
import subprocess
from textwrap import wrap


# ─────────────────────────────────────────────
# ANSI colours
# ─────────────────────────────────────────────

BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
DIM = "\033[2m"
RESET = "\033[0m"

# Claude-inspired warm palette (256-color)
ORANGE = "\033[38;5;208m"  # warm orange — primary brand accent
AMBER = "\033[38;5;214m"  # lighter amber — highlights
PEACH = "\033[38;5;216m"  # soft peach — subtle warmth
WHITE = "\033[38;5;255m"  # bright white — text on dark bg
BLUE = "\033[38;5;26m"  # cobalt blue — pixel-art headphones


# ─────────────────────────────────────────────
# Terminal helpers
# ─────────────────────────────────────────────

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def plain(s: str) -> str:
    """Strip ANSI escape sequences from *s*."""
    return _ANSI_RE.sub("", s)


def term_width() -> int:
    return shutil.get_terminal_size((100, 40)).columns


def divider(char: str = "\u2500", colour: str = DIM) -> str:
    return colour + char * term_width() + RESET


def wrap_text(text: str, indent: int = 4) -> list[str]:
    prefix = " " * indent
    lines: list[str] = []
    for para in text.splitlines():
        if para.strip() == "":
            lines.append("")
            continue
        for chunk in wrap(para, width=term_width() - indent) or [""]:
            lines.append(prefix + chunk)
    return lines


# ─────────────────────────────────────────────
# Session preview renderer
# ─────────────────────────────────────────────


def render_session_preview(session: dict, messages: list[dict]) -> str:
    lines: list[str] = []

    title = session["custom_title"] or "(no custom title)"
    sid = session["session_id"]
    date_str = (
        session["created_at"].strftime("%Y-%m-%d %H:%M")
        if session["created_at"]
        else "?"
    )

    lines.append("")
    lines.append(f"  {BOLD}{GREEN}{title}{RESET}  {DIM}({sid}){RESET}")
    lines.append(
        f"  {DIM}{date_str}  \u00b7  {len(messages)} messages  \u00b7  "
        f"{session['file_size_kb']} KB{RESET}"
    )
    lines.append(divider("\u2550", BOLD))
    lines.append("")

    if not messages:
        lines.append(f"  {DIM}(no readable messages){RESET}")
        return "\n".join(lines)

    for i, msg in enumerate(messages, 1):
        role = msg["role"]
        when = msg["when"].strftime("%H:%M:%S") if msg["when"] else ""

        if role == "user":
            role_label = f"{BOLD}{CYAN}  You{RESET}"
            body_colour = RESET
        else:
            role_label = f"{BOLD}{YELLOW}  Claude{RESET}"
            body_colour = DIM

        ts_part = f"  {DIM}{when}{RESET}" if when else ""
        lines.append(f"{role_label}{ts_part}")

        for body_line in wrap_text(msg["text"]):
            lines.append(f"{body_colour}{body_line}{RESET}")

        lines.append("")
        if i < len(messages):
            lines.append(divider("\u2500", DIM))
            lines.append("")

    lines.append(divider("\u2550", BOLD))
    lines.append(
        f"  {DIM}End of session \u00b7 press {BOLD}q{RESET}{DIM} to quit, "
        f"\u2191/\u2193 or j/k to scroll{RESET}"
    )
    lines.append("")
    return "\n".join(lines)


def open_pager(text: str) -> None:
    pager = os.environ.get("PAGER", "less")
    env = {**os.environ, "LESS": os.environ.get("LESS", "-RSXF")}
    try:
        subprocess.run([pager], input=text.encode("utf-8"), env=env)
    except FileNotFoundError:
        print(text)


# ─────────────────────────────────────────────
# Session list display
# ─────────────────────────────────────────────


def _fmt_cost(usd: float | None) -> str:
    if usd is None:
        return ""
    if usd < 0.01:
        return f"${usd:.4f}"
    return f"${usd:.2f}"


def print_sessions(sessions: list[dict], verbose: bool = False):
    if not sessions:
        print("No sessions found for this project.")
        return

    has_costs = any(s.get("total_cost") is not None for s in sessions)

    col_id = 38
    col_date = 18
    col_msg = 8
    col_size = 8
    col_cost = 10
    col_title = 50

    header_parts = [
        f"{'#':<4} ",
        f"{'Session ID':<{col_id}} ",
        f"{'Date':<{col_date}} ",
        f"{'Msgs':<{col_msg}} ",
        f"{'Size':<{col_size}} ",
    ]
    if has_costs:
        header_parts.append(f"{'Cost':<{col_cost}} ")
    header_parts.append(f"{'Title / First Message':<{col_title}}")
    header = "".join(header_parts)

    print(f"\n{BOLD}{header}{RESET}")
    print("\u2500" * len(plain(header)))

    total_cost = 0.0
    for i, s in enumerate(sessions, 1):
        date_str = (
            s["created_at"].strftime("%Y-%m-%d %H:%M") if s["created_at"] else "Unknown"
        )
        label = s["label"].replace("\n", " ")
        title_part = (
            f"{GREEN}{label[:col_title]}{RESET}"
            if s["custom_title"]
            else f"{DIM}{label[:col_title]}{RESET}"
        )

        row_parts = [
            f"{i:<4} ",
            f"{CYAN}{s['session_id']:<{col_id}}{RESET} ",
            f"{date_str:<{col_date}} ",
            f"{s['message_count']:<{col_msg}} ",
            f"{str(s['file_size_kb']) + 'KB':<{col_size}} ",
        ]
        if has_costs:
            cost = s.get("total_cost")
            if cost is not None:
                total_cost += cost
            cost_str = _fmt_cost(cost) if cost else ""
            row_parts.append(f"{YELLOW}{cost_str:<{col_cost}}{RESET} ")
        row_parts.append(f"{title_part}")

        print("".join(row_parts))
        if verbose:
            print(f"       {DIM}file: {s['file']}{RESET}")

    summary = f"\nTotal: {len(sessions)} session(s)"
    if has_costs:
        summary += f"  ·  {YELLOW}Estimated cost: {_fmt_cost(total_cost)}{RESET}"
    print(summary)
    print(
        f"({GREEN}green = custom title{RESET}, {DIM}dim = inferred from first message{RESET})"
    )
    print("\nResume:  claude --resume <session-id>")
    print("Preview: claudetool preview <session-id-or-title>")
