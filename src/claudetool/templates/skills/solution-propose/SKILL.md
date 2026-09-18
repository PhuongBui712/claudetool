---
name: solution-propose
description: Investigate an issue and propose a solution without implementing it. Small bugs and tweaks are handled inline; system architecture, integration, and security designs require plan mode and coordinated subagents. Use when the user invokes /solution-propose.
disable-model-invocation: true
---

# Solution Propose

Investigate the issue in `$ARGUMENTS` and propose a solution. Do not implement anything; the deliverable is the proposal.

## Step 1: Classify the issue

**Simple**: a small bug, a minor update, a localized change (one module, a few files, no new component).

**Complex**: anything architectural. Examples: designing a new system or a large new service, an integration solution between systems, a security solution, cross-cutting refactors, or any change that introduces new components or infrastructure.

When in doubt, treat it as complex.

## Step 2a: Simple issue

Investigate and propose yourself; do not spawn subagents.

1. Locate the relevant code and confirm the root cause with `file:line` evidence.
2. Propose the fix: which files change and what changes, in bullet points.
3. Note risks, affected callers, and the tests that should accompany the fix.
4. Offer alternatives only when a genuinely different approach exists.

## Step 2b: Complex issue

Plan mode is mandatory. Call `EnterPlanMode` before any investigation beyond a first look.

1. In plan mode, break the investigation into independent workstreams (e.g. current architecture, integration points, data flow, security surface, external constraints).
2. Spawn subagents following the project's subagent rules: simple workstream → Sonnet, complex → Fable; at most 4 concurrently; subagents must not spawn subagents. Instruct each to work with tool calls only and return a single final report.
3. Consolidate the reports into a proposal, then present it via `ExitPlanMode` for the user's approval.

The proposal covers:
- Problem statement and constraints discovered.
- Proposed architecture or solution, with components and their responsibilities.
- Data flow and integration points; security considerations where relevant.
- Trade-offs and rejected alternatives, briefly.
- Rollout or migration outline and open questions for the user.

## Output rules

- Bullet points over passages. Every claim about existing code carries a `file:line` reference.
- Separate facts found in the code from assumptions.
- Stop at the proposal. Implementation starts only when the user asks.
