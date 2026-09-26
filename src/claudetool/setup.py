"""
Setup command — scaffold a Claude Code project by copying template files.
"""

import os
import shutil
from pathlib import Path

from claudetool.rendering import BOLD, GREEN, YELLOW, DIM, RESET
from claudetool.templates import TEMPLATES_DIR, DEFAULT_OPUS_MODEL, claude_config_dir


# Files scaffolded by earlier versions; removed on `setup --force`.
DEPRECATED_AGENTS = (
    "architect.md",
    "build-error-resolver.md",
    "code-architect.md",
    "code-explorer.md",
    "code-reviewer.md",
    "code-simplifier.md",
    "coder.md",
    "database-reviewer.md",
    "e2e-runner.md",
    "fastapi-reviewer.md",
    "planner.md",
    "python-reviewer.md",
    "refactor-cleaner.md",
    "reviewer.md",
    "security-reviewer.md",
    "silent-failure-hunter.md",
    "tdd-guide.md",
    "tester.md",
)
DEPRECATED_TASKS = ("todo.md", "lessons.md")

# Global skills owned by claudetool; installed to <config dir>/skills/<name>/SKILL.md.
SKILLS_DIR = TEMPLATES_DIR / "skills"


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


def _remove_deprecated(cwd: Path) -> int:
    """Delete files scaffolded by older versions. Returns the number removed."""
    targets = [cwd / ".claude" / "agents" / n for n in DEPRECATED_AGENTS]
    targets += [cwd / "tasks" / n for n in DEPRECATED_TASKS]
    removed = 0
    for path in targets:
        if not path.is_file():
            continue
        path.unlink()
        print(f"  {YELLOW}✗{RESET}  {path.relative_to(cwd)}  {DIM}[deprecated]{RESET}")
        removed += 1
    for d in (cwd / ".claude" / "agents", cwd / "tasks"):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    return removed


def _install_skills() -> None:
    """Copy bundled skills into the user's global skills dir, touching nothing else."""
    user_skills_dir = claude_config_dir() / "skills"
    for src in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        dst = user_skills_dir / src.parent.name / "SKILL.md"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  {GREEN}✓{RESET}  {dst}  {DIM}[global]{RESET}")


def cmd_setup(args) -> None:
    cwd = Path(args.cwd or os.getcwd())
    force = args.force

    print(f"\n{BOLD}Setting up Claude Code project in:{RESET} {cwd}")
    print(f"  Config dir: {claude_config_dir()}\n")

    _copy_file(
        TEMPLATES_DIR / "settings.json",
        cwd / ".claude" / "settings.local.json",
        overwrite=force,
        label=".claude/settings.local.json  (acceptEdits + allow Bash(*), ask on dangerous patterns)",
    )
    _copy_file(
        TEMPLATES_DIR / "CLAUDE.md",
        cwd / "CLAUDE.md",
        overwrite=force,
        label="CLAUDE.md  (workflow instructions)",
    )
    removed = _remove_deprecated(cwd) if force else 0
    _install_skills()

    skills = ", ".join(
        f"/{p.parent.name}" for p in sorted(SKILLS_DIR.glob("*/SKILL.md"))
    )
    print(f"\n{BOLD}Done.{RESET}", end="")
    if removed:
        print(f"  Removed {removed} deprecated file(s).", end="")
    print(
        f"\n  Commit {DIM}.claude/settings.local.json{RESET} and "
        f"{DIM}CLAUDE.md{RESET} to share config with your team.\n"
        f"  Global skills: {DIM}{skills}{RESET}\n"
    )
    print(f"{DIM}Tip: start a session with:{RESET}")
    print(f"  claude --model {DEFAULT_OPUS_MODEL}\n")
