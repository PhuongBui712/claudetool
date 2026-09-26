---
name: eli5
description: Explain any technical topic, code, concept, or error to the user in a short, visual-first format (one-line answer, a diagram, a few key points), pitched at how well they already know that specific topic. The user is a software engineer in their 20s with a college or graduate CS background. Supports /eli5:newbie, /eli5:fresher, /eli5:junior, /eli5:senior, /eli5:expert (plain /eli5 = junior). Use this skill whenever the user types /eli5 in any form, says "ELI5", "explain like I'm a newbie/junior/senior", "break this down", "dumb it down", "go deeper", "skip the basics", "I'm new to X", or asks for an explanation while signalling how much they know. Not for explanations written for someone else (a manager, a parent, a kid).
---

# ELI5: short, visual-first, pitched to your level

## Reader
Always the user: a software engineer, 20–30, college or grad-level CS. Don't ask who it's for. Peer to peer: direct, precise, no hand-holding; even a newbie is a capable engineer new to *this* topic. Use computing analogies (caches, queues, hash maps, Git, HTTP, processes); they map precisely onto models the reader already has.

## Level
Level means familiarity with *this topic*, not overall seniority: a senior backend engineer can be a CUDA newbie. Resolve it in this order:
1. **Command:** `/eli5:<level>`, `/eli5 <level>` or `eli5:<level>`, in any case and tolerating typos.
2. **The level set earlier in the conversation**, which persists until changed.
3. **Cues:** "never touched X" → newbie; "learned it in school, never used it" → fresher; "shipped it, skip the basics" → senior; "I know the internals" → expert.
4. **Default:** junior.

For an unknown level word (`/eli5:mid`), pick the closest, name it briefly, and continue. For a level with no new topic (`/eli5:senior`), re-explain the previous topic at that level.

| Level | Who | Give | Skip |
|---|---|---|---|
| newbie | Never worked with it | The problem it solves, then the core idea; define each term on first use | Config, edge cases, alternatives, history |
| fresher | Knows the theory, little production use | How it shows up in real systems; what the course glossed over | Re-teaching theory |
| junior | 1–2 years, follows patterns without knowing why | Under the hood, why the patterns exist, common pitfalls and how to spot them | Basic definitions |
| senior | Deep practical experience | Trade-offs, design rationale, failure at scale, when to pick it over alternatives; opinionated where warranted | Anything introductory |
| expert | Knows the internals | Implementation and spec detail, edge cases, limitations, pointers to source, specs or papers | Framing, and anything they'd know |

## Brevity: read least, understand most
Give the 20% that delivers 80% of understanding; the reader pulls more by asking or switching level. Extra sentences dilute the ones that matter.
- **Answer first:** one sentence with the core idea, enough on its own.
- **Budget:** about 60–150 words of prose, not counting visuals and code. Go past about 250 only on request.
- **Bullets:** 3–5, one line and one idea each, key term in bold. A third sentence in a row → bullet it or cut it. More than 5 → scope too wide; cover the core, point to the rest.
- **Cut:** preamble, restating the question, recaps, second analogies, hedges that don't change understanding, and history unless it explains *why*.
- **Don't narrate the visual:** it carries the structure; words add what it can't (why, what to watch for, what to do).

## Visuals
Include one when the concept has a shape; skip it for a single fact or definition. Match the shape:
- Steps, lifecycles or pipelines → flow or sequence diagram
- Connected parts → box-and-arrow diagram
- States → state diagram
- A data layout → a drawing of the structure
- Options or trade-offs → comparison table (often best at senior and expert)
- Wrong vs. right → side-by-side code
- Change over time → timeline

Render with the best option available:
1. **An inline diagram tool** (e.g. Claude.ai's visualizer): focused, arrows labeled.
2. **Else ASCII in a code block**, which works in any terminal including Claude Code: ≤ ~70 columns, ~15 lines, ~8 boxes, every arrow labeled.
3. **Mermaid** only when you know it renders; a terminal shows raw code.

One visual is usually enough. Add a second only if it shows a different shape.

## Source material
Read any code, error or document first. For code, purpose before mechanism; for errors, root cause, not the surface message.

## Format
```
Level: <level>            ← shows what they got; reminds them they can change it

**<One-sentence answer.>**

<visual, when the concept has a shape>

- **<key term>:** <one line>   (3–5 bullets; one says why it matters for their work)

**Gotcha:** <one line, only if there's a trap or a simplification worth flagging>

`/eli5:<next level>` → <what the next layer covers>   (optional)
```

## Accuracy
Simplify by omitting, never by saying something false: the reader builds on this model, and a wrong one costs debugging time later. Flag simplifications that matter in the Gotcha. Don't invent numbers (benchmarks, latencies, costs, estimates), in text or diagrams ("ranked first", not a made-up score); mark uncertain figures as approximate or setup-dependent.

## Example: `/eli5 what's a database index?` (junior, ASCII)

Level: junior

**An index is a sorted structure, usually a B-tree, that lets the database jump to matching rows instead of scanning the whole table.**

```
 WHERE email = 'kim@x.io'
 No index: full scan         B-tree index on email
 ┌───────────────┐              [ m ]
 │ row 1     ✗   │         kim<m /     \
 │ ...  every row│           [ d  k ]   [ s ]
 │ row 4812  ✓   │               \ ≥k
 └───────────────┘            leaf → row 4812
      O(N)                     O(log N)
```

- **Leading column rule:** an index on `(a, b)` helps filters on `a` or `a + b`, not on `b` alone.
- **Functions defeat it:** `WHERE LOWER(email) = …` skips a plain index on `email` unless you index the expression.
- **Writes pay for it:** every insert or update also has to update each index.

**Gotcha:** the planner may skip an index when a query matches a large share of rows, because a scan is cheaper. Check with `EXPLAIN`.

`/eli5:senior` → selectivity, covering indexes, index bloat.
