# Claude Code — Project Instructions

> **Model routing via environment variables**
>
> | Env var | Purpose | Fallback |
> |---|---|---|
> | `ANTHROPIC_DEFAULT_SONNET_MODEL` | Coding & execution tasks | `sonnet-4-6` |
> | `ANTHROPIC_DEFAULT_OPUS_MODEL` | Architecture, planning & complex reasoning | `opus-4-6` |
>
> Always resolve the model at runtime:
> ```python
> import os
> SONNET = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "sonnet-4-6")
> OPUS   = os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL",   "opus-4-6")
> ```

---

## Agent Team

Claude Code supports spawning **subagents** and running **agent teams** for parallel,
context-isolated work. Use these patterns aggressively to keep the main context clean.

### When to use subagents

| Scenario | Pattern |
|---|---|
| Research / exploration | Spawn a read-only Sonnet subagent |
| Parallel feature work | One subagent per independent module |
| Code review | Dedicated Opus reviewer subagent |
| Test generation | Sonnet subagent with Write + Bash(pytest *) |
| Architecture decisions | Opus orchestrator → Sonnet implementers |

### Subagent model guidance

- **Orchestrator (lead agent)** → use `$ANTHROPIC_DEFAULT_OPUS_MODEL` (fallback `opus-4-6`):
  decomposes tasks, reviews outputs, resolves conflicts, maintains the big picture.
- **Worker subagents** → use `$ANTHROPIC_DEFAULT_SONNET_MODEL` (fallback `sonnet-4-6`):
  file reads, writes, bash, test runs, fast iteration.
- **Switch a worker to Opus** when it hits a genuinely hard reasoning problem
  (complex algorithm design, security analysis, ambiguous spec interpretation).

### Agent team operation

```
# Start with Opus as lead, agent team mode
claude --model "${ANTHROPIC_DEFAULT_OPUS_MODEL:-opus-4-6}"

# In session: switch lead to Delegate mode (Shift+Tab)
# so the lead only orchestrates and cannot edit files directly
```

Built-in subagent types available out of the box:
- **Explore** — read-only codebase navigation (Glob, Grep, Read, limited Bash)
- **Plan** — structured planning, cannot modify files

Custom subagents live in `.claude/agents/` as Markdown files with YAML frontmatter.

---

## 1. Plan Mode Default

- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs up front to reduce ambiguity

## 2. Subagent Strategy

- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution
- Default subagent model: `$ANTHROPIC_DEFAULT_SONNET_MODEL` — escalate to
  `$ANTHROPIC_DEFAULT_OPUS_MODEL` only for hard reasoning

## 3. Self-Improvement Loop

- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

## 4. Verification Before Done

- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

## 5. Demand Elegance (Balanced)

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

## 6. Autonomous Bug Fixing

- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

---

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items.
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
