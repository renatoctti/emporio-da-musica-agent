"""The agent loop: call the model, run the tools it asks for, repeat until it answers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from emporio.llm import ChatClient
from emporio.tools import Toolset

FALLBACK_REPLY = (
    "Desculpe, tive um problema para concluir essa consulta. "
    "Posso encaminhar você a um atendente da loja?"
)


@dataclass(frozen=True)
class ToolCallRecord:
    name: str
    arguments: str
    result: str


@dataclass(frozen=True)
class AgentTurn:
    reply: str
    new_messages: list[dict[str, Any]]
    tool_calls: list[ToolCallRecord]


class Agent:
    def __init__(
        self,
        client: ChatClient,
        toolset: Toolset,
        system_prompt: Callable[[], str],
        *,
        max_tool_rounds: int = 6,
    ) -> None:
        self._client = client
        self._toolset = toolset
        self._system_prompt = system_prompt
        self._max_tool_rounds = max_tool_rounds

    def reply(self, history: Sequence[dict[str, Any]], user_text: str) -> AgentTurn:
        new: list[dict[str, Any]] = [{"role": "user", "content": user_text}]
        records: list[ToolCallRecord] = []

        for _ in range(self._max_tool_rounds):
            # Rebuilt on every call so the date and the open/closed status are never stale.
            messages = [{"role": "system", "content": self._system_prompt()}, *history, *new]
            assistant = self._client.chat(messages, self._toolset.schemas)
            calls = assistant.get("tool_calls")
            if not calls:
                text = (assistant.get("content") or "").strip()
                if not text:
                    break
                new.append({"role": "assistant", "content": text})
                return AgentTurn(text, new, records)

            new.append(
                {"role": "assistant", "content": assistant.get("content"), "tool_calls": calls}
            )
            for call in calls:
                function = call["function"]
                result = self._toolset.call(function["name"], function["arguments"])
                records.append(ToolCallRecord(function["name"], function["arguments"], result))
                new.append({"role": "tool", "tool_call_id": call["id"], "content": result})

        new.append({"role": "assistant", "content": FALLBACK_REPLY})
        return AgentTurn(FALLBACK_REPLY, new, records)
