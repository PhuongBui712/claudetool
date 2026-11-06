# claudetool

A manager for Claude Code sessions stored on disk: list, inspect, search, rename, and delete them.

## Sessions

**Session**:
One top-level Claude Code conversation, stored as one transcript file per project.
_Avoid_: Conversation, chat, log

**Subagent**:
A child conversation launched from a session, by an `Agent` call or by a workflow, with its own transcript owned by that session.
_Avoid_: Sidechain, child session, task

**Turn**:
Everything from one user message up to the next one: the agent's messages and tool calls in between.

## Messages

**User message**:
What the human typed or invoked (a prompt or a slash command), excluding tool results and system-injected text.
_Avoid_: Prompt, human message, UserMsg

**Agent message**:
Text the model writes inside a turn before the turn ends.
_Avoid_: Assistant message, Claude message, AgentMsg

**Result message**:
The last agent message of a turn that ends on text: the answer the turn delivered. A turn ending on a tool call or an interruption has none.
_Avoid_: Final message, ResultMsg

**Tool call**:
One tool invocation together with its result, shown as a single unit.
_Avoid_: Tool use, tool result (as separate items)

**Meta entry**:
Text the harness injected rather than the human or the model wrote: system reminders, hook output, task notifications, subagent hand-backs.
_Avoid_: System message, injected message

## Viewing

**Block**:
One rendered unit in the viewer (a message or a tool call, plus thinking and meta entries in the expanded view); the step for message-wise navigation.

**Collapsed view**:
The default view: user, agent, and result messages in full, tool calls as a one-line summary, thinking and meta hidden.
_Avoid_: Compact mode, default mode

**Expanded view**:
The view that shows every block in full, including tool inputs and outputs, thinking, and meta entries.
_Avoid_: Verbose mode, transcript mode
