# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Bias toward caution over speed; for trivial tasks, use judgment.

## 1. Think Before Coding

- State assumptions explicitly. If uncertain or multiple interpretations exist, present them and ask; don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- Enter plan mode for any non-trivial task (3+ steps or architectural decisions).
- If something goes sideways, stop and re-plan; don't keep pushing.

## 2. Simplicity First

- Minimum code that solves the problem. No speculative features, abstractions for single-use code, unrequested configurability, or error handling for impossible scenarios.
- If 200 lines could be 50, rewrite. If a fix feels hacky, implement the elegant solution instead.
- Ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify. Skip this for simple, obvious fixes.

## 3. Surgical Changes

- Touch only what you must. Don't "improve" adjacent code, comments, or formatting; don't refactor what isn't broken.
- Match existing style, even if you'd do it differently.
- Remove imports/variables/functions that *your* change made unused. Mention pre-existing dead code; don't delete it unless asked.
- Test: every changed line traces directly to the request.

## 4. Goal-Driven Execution

- Turn tasks into verifiable goals: "Add validation" → tests for invalid inputs pass; "Fix the bug" → a reproducing test passes; "Refactor X" → tests pass before and after.
- For multi-step tasks, state a brief plan: `1. [Step] → verify: [check]`.

## 5. Verification Before Done

- Never mark a task complete without proving it works: run tests, check logs, demonstrate correctness.
- Diff behavior between main and your changes when relevant.
- Challenge your own work before presenting it. Ask: "Would a staff engineer approve this?"

## 6. Autonomous Bug Fixing

- Given a bug report, logs, errors, or failing CI: just fix it. No hand-holding, zero context switching for the user.

## 7. Code Style

Conventions for Python; apply the spirit to other languages. Match an existing file's pattern where one is established.

**Tooling**
- `ruff` (`select = ["ALL"]`, google docstrings, line length 88) and `mypy --strict`. Run `make lint` and `make format` before finishing; fix violations, don't suppress.
- Never a bare `# noqa`; always name the rule, and only when intentional. No project-wide rule disables to pass one file.

**Type hints**
- Annotate every parameter and return, including `-> None`, private helpers, and closures.
- Modern syntax: `list[str]`, `X | None`, `collections.abc` types. Never `List`, `Optional`, `Union`.
- `from __future__ import annotations` where needed; typing-only imports under `if TYPE_CHECKING:`.
- `@override` on overriding methods; `@overload` when the return type depends on arguments.
- Avoid `Any` where a precise type exists. New public parameters are keyword-only.

**Docstrings** (Google style)
- Required on every module, class, and public function. Not on `@override` methods, `@overload` stubs, or closures. Private functions: one line only if the name isn't self-explanatory.
- Simple function → a single imperative summary line. Complex function (non-obvious params, edge cases, raises, public entry point) → full `Args:`/`Returns:`/`Raises:` structure, strictly. Never a half-filled middle ground.
- A docstring is never longer than the body it documents (abstract/`Protocol` members excepted).
- Types and defaults live in the signature, not the docstring. Describe *why* and behavior, not line-by-line *what*.
- Single backticks for inline code; MkDocs `!!! warning` admonitions for callouts; American spelling.

**Comments**
- Rare and deliberate (~3–8 per 100 lines). Only for rationale, constraints/gotchas, compatibility, non-obvious branch intent, algorithm phases, or external references.
- Never narrate readable code, restate names/types, leave change-log notes, end-of-block markers, section banners, or commented-out code. Standalone line above, not trailing.

**Errors**
- Assign the message to `msg` first, then `raise ValueError(msg)`. No bare `except:`; catch the narrowest exception. Re-raise with `from e` when wrapping.

**Structure**
- Functions ~20 lines as a guideline; a readable 40-line orchestrator beats five fragments.
- Decompose by visibility: small public surface, `_private` helpers (roughly two-thirds of module functions). Private modules are `_name.py`. Every public module declares a sorted `__all__`.
- Blank lines separate logical phases, not syntactic blocks. Guard clauses first, packed together. No blank lines inside blocks under ~8 lines. A phase that needs a comment to name it, or that appears twice, becomes a helper.
- Imports: `__future__`, stdlib, third-party, first-party; absolute only; parenthesised multi-name imports one per line. Deferred imports only for cycles or load cost, with a rationale comment.

**Public API**
- Preserve exported signatures, argument order, and names. Warn before changing any public signature. Mark unstable with `@beta`, removals with `@deprecated` plus a migration hint.

**Naming**
- `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE` constants. Descriptive names; abbreviations only when universal.

**Tests**
- Every change ships with tests, unprompted: bug fix starts with a failing reproduction; feature adds tests alongside; refactor keeps tests green and covers newly touched paths. Update tests on intentional behavior change; never delete or weaken a failing test. If nothing needs a test, say why.
- Kinds: unit (`tests/unit_tests/`, offline, milliseconds, fakes for I/O), integration/e2e (`tests/integration_tests/`, skip cleanly without credentials), smoke (imports, `__all__`, default construction). New implementations of a shared interface plug into the shared contract suite.
- Cover behavior, not lines: happy path, edge cases (empty, single, boundaries, `None`, unicode, ordering), every `Raises:` entry, sync and async, streaming/batch variants, backwards compatibility, serialization round-trips. Prefer `parametrize` over copy-paste; many small tests over one scenario.
- Test files mirror the source tree; names describe behavior (`test_split_text_returns_empty_list_for_empty_input`). One behavior per test; assert outcomes, not internal calls. Never `skip`/`xfail` to hide a real failure.

**Self-check before finishing**: annotations complete and `mypy --strict` clean; docstrings either one-liner or full Google form, never longer than the body; comments explain *why*; every `raise` uses `msg`; `__all__` sorted; tests cover happy/edge/error paths; `make lint` and `make format` clean.

## 8. Git Convention

- Follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
- Commits, MR titles, and descriptions are brief: summarize the change and its purpose. If length is unavoidable, split into short bullet points; avoid prose passages.
- MR descriptions: bullet points of the main changes only. No deploy or test sections unless strictly required.
- Never create a git worktree on your own. When the user names a branch, the default intent is to check it out and edit there. Create a worktree only when the user explicitly asks for one.
- Never include author, co-author, or collaborator information in commits or MRs.

## 9. Subagents

- For complex, multi-step work (code + test + integrate, many changes across files), prefer coordinating subagents to complete the task.
- Model choice: simple task → Sonnet; complex task → Fable. Choose effort yourself; don't overuse high effort.
- In subagent prompts, ask for tool calls until the task is done and a single final report; discourage intermediate text output, which adds little value.
- At most 4 subagents at a time. Subagents must not spawn further subagents.
