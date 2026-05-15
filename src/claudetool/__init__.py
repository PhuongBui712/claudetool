from importlib.metadata import version as _version

__version__ = _version("claudetool")

# Modern Claude-inspired logo using Unicode box-drawing + sparkle motif
# Rendered with warm orange/amber colors at display time
ASCII_LOGO = """\
      \u2727
   \u2727     \u2727
     \u2727 \u2727       \u2501\u2501\u2501  claudetool
   \u2727     \u2727
      \u2727"""


# Colorized banner builder — called by cli.py and quickstart.py
def render_logo(version: bool = True) -> str:
    from claudetool.rendering import ORANGE, AMBER, DIM, PEACH, BOLD, RESET

    def orange(c):
        return f"{BOLD}{ORANGE}{c}{RESET}"

    def amber(c):
        return f"{AMBER}{c}{RESET}"

    def dim(c):
        return f"{DIM}{c}{RESET}"

    lines = [
        f"              {orange('╻')}",
        f"           {amber('╲')}  {orange('╻')}  {amber('╱')}",
        f"         {amber('╲')}  {amber('╲')} {orange('╻')} {amber('╱')}  {amber('╱')}",
        f"  {dim('──')}  {dim('───')}{orange('╋')}{dim('───')}{orange('╸')}{dim('──')}        {BOLD}{ORANGE}claudetool{RESET}",
        f"         {amber('╱')}  {amber('╱')} {orange('╹')} {amber('╲')}  {amber('╲')}",
        f"           {amber('╱')}  {orange('╹')}  {amber('╲')}",
    ]

    if version:
        lines[4] += f"   {DIM}v{__version__}{RESET}"
        lines[5] += f"      {PEACH}Session Manager for Claude Code{RESET}"

    return "\n".join(lines)
