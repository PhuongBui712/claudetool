---
name: quick
description: Confirm a fact, run a quick check, or explain something briefly based on the current codebase. Read-only; never implements or edits source code. Use when the user invokes /quick.
disable-model-invocation: true
---

# Quick

Answer the question in `$ARGUMENTS` from the current codebase. This is a read-only skill.

## Rules

- Do not edit, create, or delete any file. Do not run commands that change state.
- Read only what is needed to answer. Prefer targeted `grep`/`Read` over broad exploration.
- Spawning subagents is not allowed; a quick check must stay cheap.
- If the answer cannot be confirmed from the code, say so plainly instead of guessing.

## Output

- Lead with the verdict: confirmed / not confirmed / partially, or the direct answer.
- Follow with the evidence: `file:line` references and a one-line explanation each.
- Keep it short. No plan, no implementation proposal, no follow-up offer.
- If the user's assumption is wrong, state what is actually true and where it is defined.
