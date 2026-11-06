# claudetool

Claude Code session manager — list, inspect, and delete sessions globally.

## Install

```bash
pip install -e /path/to/claudetool
# or from the repo root:
pip install -e .
```

## Usage

```bash
# List sessions for current project
claudetool

# List with full file paths
claudetool -v

# List for a specific project directory
claudetool --cwd /path/to/project

# Open one session's transcript directly
claudetool preview d2d9fe9a

# Search message text across this project's sessions
claudetool search "QuickSight" --limit 20

# ── Delete ──────────────────────────────────────────

# Delete by session ID prefix
claudetool delete d2d9fe9a

# Delete by custom title (case-insensitive substring)
claudetool delete "Backend refactor"

# Delete multiple sessions
claudetool delete d2d9fe9a 643aa5b4 "Auth fix"

# Delete ALL sessions
claudetool delete --all

# Delete ALL except specific sessions (by ID prefix or title)
claudetool delete --all --except d2d9fe9a 643aa5b4

# Preview without deleting
claudetool delete --all --dry-run

# Skip confirmation prompt
claudetool delete --all --yes
```

## Keys

| Screen | Keys |
|---|---|
| Session list | `j/k` move · `Enter` open · `/` filter by title/id · `Ctrl+F` search content · `r` rename · `d` delete · `q` quit |
| Transcript | `j/k` previous/next block · mouse wheel scrolls lines · `g/G` top/bottom · `Ctrl+O` collapsed/expanded · `/` search, `n/N` next/previous · `Enter` on an Agent call opens the subagent · `a` subagent list · `Esc` back |
| Everywhere | `Ctrl+C` quits |
