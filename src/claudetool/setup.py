"""
Setup command — scaffold a Claude Code project by copying template files.
"""

import os
import shutil
from pathlib import Path

from claudetool.rendering import BOLD, GREEN, YELLOW, DIM, RESET
from claudetool.templates import TEMPLATES_DIR, DEFAULT_OPUS_MODEL


CATEGORIES = ("default", "python", "security", "beta")
EXTRA_CATEGORIES = tuple(c for c in CATEGORIES if c != "default")


def _copy_file(src: Path, dst: Path, overwrite: bool, label: str) -> bool:
    """Copy *src* to *dst*. Returns True if written, False if skipped."""
    if dst.exists() and not overwrite:
        print(
            f"  {YELLOW}skip{RESET}  {label}  {DIM}(already exists — use --force to overwrite){RESET}"
        )
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  {GREEN}✓{RESET}  {label}")
    return True


def _parse_with(raw: str | None) -> set[str]:
    """Parse the --with flag value into a set of extra categories."""
    if not raw:
        return set()
    parts = {p.strip() for p in raw.split(",") if p.strip()}
    if "all" in parts:
        return set(EXTRA_CATEGORIES)
    invalid = parts - set(CATEGORIES)
    if invalid:
        valid = ",".join(EXTRA_CATEGORIES) + ",all"
        raise SystemExit(
            f"Unknown --with category: {', '.join(sorted(invalid))}. Valid: {valid}"
        )
    parts.discard("default")  # default is always included
    return parts


def _collect_agent_files(legacy: bool, extras: set[str]) -> list[tuple[Path, str]]:
    """Return list of (src_path, category_label) for agent files to copy."""
    if legacy:
        legacy_dir = TEMPLATES_DIR / "legacy" / "agents"
        return [(p, "legacy") for p in sorted(legacy_dir.glob("*.md"))]

    wanted = ["default", *sorted(extras)]
    files: list[tuple[Path, str]] = []
    for cat in wanted:
        cat_dir = TEMPLATES_DIR / "agents" / cat
        files.extend((p, cat) for p in sorted(cat_dir.glob("*.md")))
    return files


def cmd_setup(args) -> None:
    cwd = Path(args.cwd or os.getcwd())
    force = args.force
    legacy = bool(getattr(args, "legacy", False))
    extras = set() if legacy else _parse_with(getattr(args, "with_", None))

    mode_label = "legacy (V1)" if legacy else "v2"
    extras_label = ", ".join(sorted(extras)) if extras else "—"
    print(f"\n{BOLD}Setting up Claude Code project in:{RESET} {cwd}")
    print(f"  Mode    : {mode_label}")
    print(f"  Extras  : {extras_label}\n")

    # ── 1. .claude/settings.local.json ──────────────────────────────────
    _copy_file(
        TEMPLATES_DIR / "settings.json",
        cwd / ".claude" / "settings.local.json",
        overwrite=force,
        label=".claude/settings.local.json  (acceptEdits + allow Bash(*), ask on dangerous patterns)",
    )

    # ── 2. CLAUDE.md ──────────────────────────────────────────────────
    claude_md_src = TEMPLATES_DIR / ("legacy/CLAUDE.md" if legacy else "CLAUDE.md")
    _copy_file(
        claude_md_src,
        cwd / "CLAUDE.md",
        overwrite=force,
        label=f"CLAUDE.md  ({'V1' if legacy else 'V2'} workflow instructions)",
    )

    # ── 3. .claude/agents/ ────────────────────────────────────────────
    agent_files = _collect_agent_files(legacy, extras)
    for src_file, cat in agent_files:
        _copy_file(
            src_file,
            cwd / ".claude" / "agents" / src_file.name,
            overwrite=force,
            label=f".claude/agents/{src_file.name}  {DIM}[{cat}]{RESET}",
        )

    # ── 4. tasks/ scaffold ───────────────────────────────────────────
    tasks_src = TEMPLATES_DIR / "tasks"
    for src_file in sorted(tasks_src.iterdir()):
        _copy_file(
            src_file,
            cwd / "tasks" / src_file.name,
            overwrite=False,
            label=f"tasks/{src_file.name}",
        )

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{BOLD}Done.{RESET}  Installed {len(agent_files)} agent(s).")
    print(
        f"  Commit {DIM}.claude/settings.local.json{RESET} and "
        f"{DIM}CLAUDE.md{RESET} to share config with your team.\n"
    )
    print(f"{DIM}Tip: start a session with the Opus orchestrator:{RESET}")
    print(f"  claude --model {DEFAULT_OPUS_MODEL}\n")
