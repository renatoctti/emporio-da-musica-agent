"""Keeps the history sent to the model within a size budget, with no model call.

The model gets the whole conversation on every call, tool results included, and one product or
manual result can be thousands of characters. Only what is sent is shortened; what is saved in the
database is not touched, and the verification state lives in code, not in the messages.

Order of removal, from least to most needed: the results of old tool calls (the answer that
followed already used them), then the oldest whole turns. The last turns are always kept intact.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

MAX_HISTORY_CHARS = 40_000  # about 10 thousand tokens: a normal conversation is never changed
KEEP_TURNS = 2
OMITTED_RESULT = json.dumps(
    {
        "omitted": True,
        "note": "Older tool result removed to save context; the answer after it used it.",
    }
)


def _size(messages: Sequence[dict[str, Any]]) -> int:
    return sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)


def _turns(history: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Whole turns: each starts at a customer message and runs to just before the next one."""
    turns: list[list[dict[str, Any]]] = []
    for message in history:
        if message.get("role") == "user" or not turns:
            turns.append([])
        turns[-1].append(message)
    return turns


def _without_result(message: dict[str, Any]) -> dict[str, Any]:
    if message.get("role") == "tool":
        return {
            **message,
            "content": OMITTED_RESULT,
        }  # the tool_call_id stays, so calls stay paired
    return message


def _flatten(turns: Sequence[Sequence[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [message for turn in turns for message in turn]


def compact_history(
    history: Sequence[dict[str, Any]],
    max_chars: int = MAX_HISTORY_CHARS,
    keep_turns: int = KEEP_TURNS,
) -> list[dict[str, Any]]:
    if _size(history) <= max_chars:
        return list(history)
    turns = _turns(history)
    split = max(0, len(turns) - keep_turns)
    older = [[_without_result(m) for m in turn] for turn in turns[:split]]
    recent = turns[split:]
    while older and _size(_flatten([*older, *recent])) > max_chars:
        older.pop(0)  # whole turns only, so no tool message is left without its call
    return _flatten([*older, *recent])
