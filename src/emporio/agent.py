"""The agent loop: call the model, run the tools it asks for, repeat until it answers."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from emporio.llm import ChatClient
from emporio.metrics import TurnMetrics
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
    metrics: TurnMetrics = field(default_factory=TurnMetrics)


def _usage(client: ChatClient) -> dict[str, int]:
    """Running token totals, for clients that keep them (the real one does, the fakes do not)."""
    usage = getattr(client, "usage", None)
    return dict(usage) if isinstance(usage, dict) else {}


class Agent:
    def __init__(
        self,
        client: ChatClient,
        toolset: Toolset,
        system_prompt: Callable[[], str],
        *,
        max_tool_rounds: int = 6,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._client = client
        self._toolset = toolset
        self._system_prompt = system_prompt
        self._max_tool_rounds = max_tool_rounds
        self._clock = clock

    def reply(self, history: Sequence[dict[str, Any]], user_text: str) -> AgentTurn:
        started = self._clock()
        usage_before = _usage(self._client)
        new: list[dict[str, Any]] = [{"role": "user", "content": user_text}]
        records: list[ToolCallRecord] = []
        model_calls = 0

        def finish(text: str) -> AgentTurn:
            usage_after = _usage(self._client)
            metrics = TurnMetrics(
                latency_ms=round((self._clock() - started) * 1000),
                model_calls=model_calls,
                tool_calls=len(records),
                prompt_tokens=usage_after.get("prompt_tokens", 0)
                - usage_before.get("prompt_tokens", 0),
                completion_tokens=usage_after.get("completion_tokens", 0)
                - usage_before.get("completion_tokens", 0),
            )
            new.append({"role": "assistant", "content": text})
            return AgentTurn(text, new, records, metrics)

        for _ in range(self._max_tool_rounds):
            # Rebuilt on every call so the date and the open/closed status are never stale.
            messages = [{"role": "system", "content": self._system_prompt()}, *history, *new]
            assistant = self._client.chat(messages, self._toolset.schemas)
            model_calls += 1
            calls = assistant.get("tool_calls")
            if not calls:
                text = (assistant.get("content") or "").strip()
                if not text:
                    break
                return finish(text)

            new.append(
                {"role": "assistant", "content": assistant.get("content"), "tool_calls": calls}
            )
            for call in calls:
                function = call["function"]
                result = self._toolset.call(function["name"], function["arguments"])
                records.append(ToolCallRecord(function["name"], function["arguments"], result))
                new.append({"role": "tool", "tool_call_id": call["id"], "content": result})

        return finish(FALLBACK_REPLY)
