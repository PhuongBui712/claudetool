"""
Quickstart command — interactive getting-started guide for new users.
"""

from claudetool import render_logo
from claudetool.rendering import (
    BOLD,
    CYAN,
    DIM,
    RESET,
    ORANGE,
    AMBER,
    PEACH,
)
from claudetool.templates import DEFAULT_OPUS_MODEL


def cmd_quickstart(args) -> None:
    # ── Logo ─────────────────────────────────────────────────────────
    print()
    print(render_logo(version=True))
    print()
    print(
        f"  {DIM}\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500{RESET}"
    )
    print()

    # ── Getting started ──────────────────────────────────────────────
    print(f"  {ORANGE}\u25c6{RESET} {BOLD}Getting Started{RESET}")
    print()

    icons = ["\u25b8", "\u25b8", "\u25b8", "\u25b8", "\u25b8"]
    steps = [
        ("claudetool setup", "Scaffold settings, CLAUDE.md, and agents"),
        (f"claude --model {DEFAULT_OPUS_MODEL}", "Start a Claude Code session"),
        ("claudetool list", "See all sessions with cost estimates"),
        ("claudetool preview <id>", "Read back a session conversation"),
        ("claudetool delete <id>", "Clean up old sessions"),
    ]
    for i, ((cmd, desc), icon) in enumerate(zip(steps, icons), 1):
        print(f"    {AMBER}{icon}{RESET}  {BOLD}{i}.{RESET}  {CYAN}{cmd}{RESET}")
        print(f"          {DIM}{desc}{RESET}")
        print()

    # ── Commands ─────────────────────────────────────────────────────
    print(f"  {ORANGE}\u25c6{RESET} {BOLD}Commands{RESET}")
    print()

    commands = [
        ("\u2630", "list", "List all sessions with metadata and cost estimates"),
        ("\u25b6", "preview", "Preview session messages in a scrollable pager"),
        ("\u2315", "search", "Full-text search across all sessions"),
        ("\u2261", "stats", "Token usage and cost summary per session"),
        (
            "\u2699",
            "setup",
            "Scaffold .claude/settings.json, CLAUDE.md, agents, tasks/",
        ),
        ("\u2716", "delete", "Delete sessions by ID, title, or --all"),
        ("\u2727", "quickstart", "Show this getting-started guide"),
    ]
    for icon, name, desc in commands:
        print(f"    {AMBER}{icon}{RESET}  {CYAN}{name:<12}{RESET}  {desc}")
    print()

    # ── Tips ─────────────────────────────────────────────────────────
    print(f"  {ORANGE}\u25c6{RESET} {BOLD}Tips{RESET}")
    print()
    tips = [
        ("Run {cmd}claudetool setup --force{end} to regenerate config files."),
        ("Use {cmd}claudetool search{end} to find conversations across all sessions."),
        ("Check {cmd}claudetool stats{end} to track token spend and model usage."),
        ("Sessions are stored per-project under {dim}~/.claude/projects/{end}."),
    ]
    for tip in tips:
        formatted = tip.format(cmd=CYAN, dim=DIM, end=RESET)
        print(f"    {AMBER}\u2727{RESET}  {formatted}")
    print()

    # ── Footer ───────────────────────────────────────────────────────
    print(
        f"  {DIM}\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500{RESET}"
    )
    print(f"  Run {CYAN}claudetool <command> --help{RESET} for detailed options.")
    print(f"  {PEACH}Powered by Claude Code{RESET}  {DIM}\u2727{RESET}\n")
