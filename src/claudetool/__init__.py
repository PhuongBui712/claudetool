from importlib.metadata import version as _version

__version__ = _version("claudetool")

# Pixel-art mascot: orange blob with cobalt-blue headphones, sleepy eyes,
# four little legs. Each character row encodes 2 vertical pixels via ▀/▄/█.
ASCII_LOGO = """\
  ▄▄▀▀▀▀▀▀▀▀▄▄
▄█▀▄████████▄▀█▄
████▄▄████▄▄████
 ██▀▀██▀▀██▀▀██"""


# Colorized banner builder — called by cli.py and quickstart.py
def render_logo(version: bool = True) -> str:
    from claudetool.rendering import ORANGE, BLUE, DIM, PEACH, BOLD, RESET

    OR = ORANGE
    BL = f"{BOLD}{BLUE}"
    R = RESET

    lines = [
        f"  {BL}▄▄▀▀▀▀▀▀▀▀▄▄{R}  ",
        f"{BL}▄█▀{R}{OR}▄████████▄{R}{BL}▀█▄{R}",
        f"{BL}██{R}{OR}██▄▄████▄▄██{R}{BL}██{R}",
        f" {OR}██▀▀██▀▀██▀▀██{R} ",
    ]

    if version:
        lines[1] += f"   {BOLD}{ORANGE}claudetool{R}"
        lines[2] += f"   {DIM}v{__version__}{R}"
        lines[3] += f"   {PEACH}Session Manager for Claude Code{R}"

    return "\n".join(lines)
