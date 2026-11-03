# Spec 19: Context budget for long conversations

**Status:** 🟢 Implemented
**Author:** renatoctti
**Date:** 2026-11-02
**Scope:** keep the history sent to the model within a size budget, without extra model calls
**Depends on:** 08, 14
**Delivery:** autonomous (after its dependencies)

---

## Summary

Every model call resends the whole conversation, tool results included, and a single product or
manual result can be several thousand characters. In a long chat the cost and the latency grow with
every message and the conversation can eventually exceed the context window. This spec keeps the
history that is sent within a character budget by removing what the agent needs least, in a fixed
order, and never touches what is stored in the database.

## Context

The identity check and the other session state live in code, not in the messages, so removing old
messages cannot make the agent forget who is verified. The compaction is deterministic and needs no
model call: first the results of old tool calls are replaced by a short note (the text of the answer
already says what mattered), then, if the budget is still exceeded, the oldest whole turns are
dropped. The latest turns are always kept intact.

---

## Allowed files

**Production:** src/emporio/context.py (new); src/emporio/agent.py (applies it)

**Tests:** tests/test_context.py (new)

**Docs:** README.md, PROJECT_MAP.md

**Do not touch:** what is saved in the database, the tools and the prompt.

---

## Functional requirements

| ID | Requirement | Priority | Acceptance |
|---|---|---|---|
| ✅ RF-01 | compact_history returns the history unchanged (as a new list) when its size is within the budget | Must | Unit test |
| ✅ RF-02 | Over the budget, the tool results of every turn except the last two are replaced by a short JSON note; every tool message keeps its tool_call_id so the calls stay paired | Must | Unit test on pairing |
| ✅ RF-03 | If it is still over the budget, the oldest whole turns are dropped, never the last two, and the first message that remains is a customer message | Must | Unit test |
| ✅ RF-04 | The input is never modified and the result is deterministic | Must | Unit test |
| ✅ RF-05 | Agent.reply sends the compacted history to the model; the list it receives and the database keep the full conversation | Must | Agent test with a fake client |

## Non-functional requirements

- No model call and no new dependency.
- The default budget is generous (about 40 thousand characters), so a normal conversation is never changed.

## Out of scope

- Summaries written by a model (they cost a call and can invent details) and long-term memory across sessions.

## Test checklist

- [x] ✅ Within the budget, tool results, dropping turns, purity
- [x] ✅ The agent sends the compacted history and keeps the full one
