"""
CLI entry point — argparse setup, command dispatch.

This is the composition layer that wires together sessions, rendering,
setup, and quickstart modules.
"""

import os
import argparse

from claudetool import render_logo
from claudetool.rendering import (
    RED,
    YELLOW,
    RESET,
    print_sessions,
    render_session_preview,
    open_pager,
)
from claudetool.sessions import (
    list_sessions_filesystem,
    parse_messages,
    resolve_targets,
    delete_sessions,
    confirm,
)
from claudetool.setup import cmd_setup
from claudetool.quickstart import cmd_quickstart
from claudetool.search import cmd_search
from claudetool.stats import cmd_stats, get_session_total_cost
from claudetool.tui import run_interactive


# ─────────────────────────────────────────────
# Argument parser
# ─────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    version_text = render_logo(version=True)

    p = argparse.ArgumentParser(
        description="Claude Code Session Manager — list, preview, setup, and delete sessions.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--version", "-V", action="version", version=version_text)
    p.add_argument(
        "--cwd", metavar="DIR", help="Project directory (default: current directory)"
    )
    p.add_argument(
        "--verbose", "-v", action="store_true", help="Show full file paths in list"
    )

    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    # ── list ─────────────────────────────────
    sub.add_parser("list", help="List all sessions (default)")

    # ── preview ──────────────────────────────
    pre_p = sub.add_parser(
        "preview",
        help="Preview messages of a session in a scrollable pager (q to quit)",
    )
    pre_p.add_argument(
        "target",
        metavar="ID_OR_TITLE",
        help="Session ID prefix or custom title (case-insensitive substring match)",
    )

    # ── setup ────────────────────────────────
    setup_p = sub.add_parser(
        "setup",
        help=(
            "Scaffold .claude/settings.json, CLAUDE.md, "
            ".claude/agents/, and tasks/ in the current project"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    setup_p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files (default: skip files that already exist)",
    )
    setup_p.add_argument(
        "--with",
        dest="with_",
        metavar="CATS",
        default=None,
        help=(
            "Comma-separated extra agent categories to include alongside the\n"
            "default set. Valid: python, security, beta, all\n"
            "Examples:\n"
            "  --with python\n"
            "  --with python,security\n"
            "  --with all"
        ),
    )
    setup_p.add_argument(
        "--legacy",
        action="store_true",
        help="Use the V1 CLAUDE.md and the original 4-agent set (architect/coder/reviewer/tester)",
    )

    # ── delete ───────────────────────────────
    del_p = sub.add_parser(
        "delete",
        help="Delete sessions",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    del_p.add_argument(
        "targets",
        nargs="*",
        metavar="ID_OR_TITLE",
        help="Session IDs (or prefixes) / custom titles to delete.",
    )
    del_p.add_argument(
        "--all", action="store_true", help="Delete ALL sessions in this project"
    )
    del_p.add_argument(
        "--except",
        dest="keep",
        nargs="+",
        metavar="ID_OR_TITLE",
        help="With --all: keep sessions matching these IDs/titles",
    )
    del_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without deleting",
    )
    del_p.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation prompt"
    )

    # ── search ────────────────────────────────
    search_p = sub.add_parser(
        "search",
        help="Full-text search across all sessions",
    )
    search_p.add_argument(
        "query",
        metavar="QUERY",
        help="Text to search for (case-insensitive)",
    )
    search_p.add_argument(
        "--since",
        metavar="DATE",
        help="Only search messages after this date (YYYY-MM-DD)",
    )
    search_p.add_argument(
        "--limit",
        type=int,
        default=50,
        metavar="N",
        help="Maximum number of results (default: 50)",
    )

    # ── stats ─────────────────────────────────
    stats_p = sub.add_parser(
        "stats",
        help="Token usage and cost summary",
    )
    stats_p.add_argument(
        "--session",
        metavar="ID_OR_TITLE",
        help="Drill into a specific session",
    )
    stats_p.add_argument(
        "--since",
        metavar="DATE",
        help="Only include sessions after this date (YYYY-MM-DD)",
    )

    # ── quickstart ───────────────────────────
    sub.add_parser("quickstart", help="Interactive getting-started guide")

    return p


# ─────────────────────────────────────────────
# Command handlers
# ─────────────────────────────────────────────


def cmd_list(sessions, verbose):
    print_sessions(sessions, verbose=verbose)


def cmd_preview(sessions, args):
    matched = resolve_targets(sessions, [args.target])
    if not matched:
        print(f"{RED}No session matched:{RESET} {args.target}")
        print("Run `claudetool list` to see available sessions.")
        return
    if len(matched) > 1:
        print(
            f"{YELLOW}Multiple sessions matched — showing the most recent one.{RESET}"
        )
        print("Use a longer ID prefix to target a specific session.\n")
    session = matched[0]
    messages = parse_messages(session["file"])
    rendered = render_session_preview(session, messages)
    open_pager(rendered)


def cmd_delete(sessions, args):
    if not sessions:
        print("No sessions to delete.")
        return

    if args.all:
        if args.keep:
            keep_set = {s["session_id"] for s in resolve_targets(sessions, args.keep)}
            targets = [s for s in sessions if s["session_id"] not in keep_set]
            kept = [s for s in sessions if s["session_id"] in keep_set]
            print(f"\nKeeping {len(kept)} session(s):")
            for s in kept:
                print(f"  \u2713  {s['custom_title'] or s['session_id']}")
        else:
            targets = sessions
    elif args.targets:
        targets = resolve_targets(sessions, args.targets)
        if not targets:
            print(f"No sessions matched: {', '.join(args.targets)}")
            return
    else:
        print("Specify session IDs/titles, or use --all.")
        return

    if not targets:
        print("No sessions to delete after applying filters.")
        return

    print(
        f"\n{'[DRY RUN] ' if args.dry_run else ''}Sessions to delete ({len(targets)}):"
    )
    for s in targets:
        date_str = (
            s["created_at"].strftime("%Y-%m-%d %H:%M") if s["created_at"] else "?"
        )
        label = s["custom_title"] or f"(no title) {s['session_id'][:16]}\u2026"
        print(f"  \u2022 {label:<50}  {date_str}  {s['file_size_kb']} KB")

    if args.dry_run:
        delete_sessions(targets, dry_run=True)
        return

    if not args.yes:
        if not confirm(f"\nPermanently delete {len(targets)} session(s)?"):
            print("Aborted.")
            return

    count = delete_sessions(targets, dry_run=False)
    print(f"\n{count} session(s) deleted.")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────


def main():
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "list"

    if command == "setup":
        cmd_setup(args)
        return

    if command == "quickstart":
        cmd_quickstart(args)
        return

    # All other commands need the session list
    cwd = args.cwd or os.getcwd()
    verbose = args.verbose

    print(f"Project : {cwd}")

    sessions = list_sessions_filesystem(cwd)

    if command == "list":
        # Enrich with cost data for the list table
        for s in sessions:
            s["total_cost"] = get_session_total_cost(s["file"])
        if verbose:
            cmd_list(sessions, verbose)
        else:
            run_interactive(sessions, cwd)
    elif command == "preview":
        cmd_preview(sessions, args)
    elif command == "delete":
        cmd_delete(sessions, args)
    elif command == "search":
        cmd_search(sessions, args)
    elif command == "stats":
        cmd_stats(sessions, args)
    else:
        for s in sessions:
            s["total_cost"] = get_session_total_cost(s["file"])
        run_interactive(sessions, cwd)


if __name__ == "__main__":
    main()
