"""
Terminal rendering — ANSI colours, text helpers, session display.

Everything related to "how things look in the terminal" lives here.
This module receives data and formats it; it does not fetch or parse anything.
"""

from __future__ import annotations

import re
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claudetool.sessions import Session


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


# ─────────────────────────────────────────────
# Session list display
# ─────────────────────────────────────────────


def _fmt_cost(usd: float | None) -> str:
    if usd is None:
        return ""
    if usd < 0.01:
        return f"${usd:.4f}"
    return f"${usd:.2f}"


def print_sessions(sessions: list[Session], verbose: bool = False) -> None:
    if not sessions:
        print("No sessions found for this project.")
        return

    col_id, col_date, col_prompts, col_size, col_cost, col_title = 38, 17, 8, 9, 9, 50
    has_costs = any(s["total_cost"] is not None for s in sessions)

    header = (
        f"{'#':<4} {'Session ID':<{col_id}} {'Last active':<{col_date}} "
        f"{'Prompts':>{col_prompts}} {'Size':>{col_size}} "
        f"{'Cost':>{col_cost}} Title"
    )
    print(f"\n{BOLD}{header}{RESET}")
    print("\u2500" * len(header))

    total_cost = 0.0
    for i, s in enumerate(sessions, 1):
        label = s["label"].replace("\n", " ")[:col_title]
        colour = GREEN if s["custom_title"] else DIM
        prompts = "\u2013" if s["prompt_count"] is None else str(s["prompt_count"])
        cost = s["total_cost"]
        total_cost += cost or 0.0
        print(
            f"{i:<4} {CYAN}{s['session_id']:<{col_id}}{RESET} "
            f"{s['last_active'].strftime('%Y-%m-%d %H:%M'):<{col_date}} "
            f"{prompts:>{col_prompts}} "
            f"{str(s['file_size_kb']) + 'KB':>{col_size}} "
            f"{YELLOW}{_fmt_cost(cost) or '\u2013':>{col_cost}}{RESET} "
            f"{colour}{label}{RESET}"
        )
        if verbose:
            print(f"       {DIM}file: {s['file']}{RESET}")

    summary = f"\nTotal: {len(sessions)} session(s)"
    if has_costs:
        summary += f"  \u00b7  {YELLOW}Estimated cost: {_fmt_cost(total_cost)}{RESET}"
    print(summary)
    print(
        f"({GREEN}green = custom title{RESET}, {DIM}dim = inferred from first message{RESET})"
    )
    print("\nResume:  claude --resume <session-id>")
    print("Preview: claudetool preview <session-id-or-title>")
