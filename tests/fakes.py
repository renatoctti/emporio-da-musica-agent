"""Test doubles shared by the agent, CLI and eval tests."""

from __future__ import annotations

import copy
import json
from typing import Any


def tool_call(call_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def assistant_calls(*calls: dict[str, Any], content: str | None = None) -> dict[str, Any]:
    return {"role": "assistant", "content": content, "tool_calls": list(calls)}


def assistant_text(text: str | None) -> dict[str, Any]:
    return {"role": "assistant", "content": text}


class FakeChatClient:
    """Returns the scripted assistant messages in order and records what it was asked."""

    def __init__(self, script: list[dict[str, Any]], *, repeat_last: bool = False) -> None:
        self._script = list(script)
        self._repeat_last = repeat_last
        self.calls: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]] = []

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls.append((copy.deepcopy(messages), tools))
        if not self._script:
            raise AssertionError("FakeChatClient script exhausted")
        if self._repeat_last and len(self._script) == 1:
            return copy.deepcopy(self._script[0])
        return self._script.pop(0)
