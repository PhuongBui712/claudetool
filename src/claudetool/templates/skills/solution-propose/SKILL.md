---
name: solution-propose
description: Investigate an issue and propose solutions without implementing them. Use when the user invokes /solution-propose.
disable-model-invocation: true
---

# Solution Propose

Investigate the issue in `$ARGUMENTS` and deliver a proposal. The work is read-only; implementation starts only when the user asks.

## 1. Clarify what blocks

If a missing constraint would change which solution you propose (scope, size, what must stay unchanged), ask it in one `AskUserQuestion` call before investigating. Otherwise start, and label your assumptions in the proposal.

## 2. Investigate

Investigate yourself. Fan out to subagents only when the work splits into independent workstreams too large for one context:

- `Explore` type, with `model` and `effort` passed explicitly per workstream (when unsure, one tier up):
  - **Haiku** · low: lookups with no judgement: find files or symbols, list ids or usages, dump a schema or config.
  - **Sonnet** · medium: explain one bounded area: trace a flow, describe how a module works today, sample a table.
  - **Opus** · high: judgement the recommendation rests on: compare designs, security surface, cross-system integration, metric or logic definitions.
- At most 6 concurrently. Subagents use tool calls only, spawn none, and return one report separating facts (with evidence) from inferences.
- Reports are leads: re-check every claim the recommendation rests on against the source.

Done when every claim the recommendation rests on has evidence: `file:line` for code, otherwise the concrete id (table.column, QuickSight dataset or visual id, Jira key, config path). A bug whose root cause the evidence can't confirm gets that said plainly, with `/diagnosing-bugs` as the recommended next step.

## 3. Propose

Bullets over prose, in this order:

1. **Summary**: 2–3 lines, the recommendation and why.
2. **Facts**: what exists today, each with its evidence; inferences labelled.
3. **Recommended option**: what changes where, risks, affected callers, accompanying tests. For a new component or system, also its responsibilities, data flow, integration points, security, and rollout.
4. **Alternative**: one option of clearly different size, labelled smaller or bolder.
5. **Changes you'd notice**: anything that alters current behaviour or definitions (timezone, granularity, metric formulas, defaults). "None" when nothing does.
6. **Rejected**: one line each.
7. **Handoff**: one line, e.g. `/goal implement the recommended option`.

Close with one `AskUserQuestion` call: which option to go with, plus up to 3 open questions. Then stop.
