"""The same agent as a LangGraph graph: a `call_model` node, a `run_tools` node and the edges
between them.

`GraphAgent` takes the arguments of `emporio.agent.Agent` and returns the same `AgentTurn`, so
the evaluation, the tests and the CLI can use either. The model client, the tools, the prompt and
the history compaction are the very same objects; only the loop is drawn as a graph:

    START -> call_model --(tool calls)--> run_tools --(rounds left)--> call_model
                  |                            |
                  +--(text, or empty)--> END <-+--(round limit)

What the graph buys is a state that is explicit and a place to pause (an `interrupt` before a
tool, a checkpointer to resume a conversation). What it costs is a dependency and about twice the
code. `tests/test_graph_agent.py` checks that, for the same scripted model, both loops produce the
same turn. `langgraph` is an optional dependency: `pip install -e ".[graph]"`.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from emporio.agent import FALLBACK_REPLY, AgentTurn, ToolCallRecord, _usage
from emporio.context import MAX_HISTORY_CHARS, compact_history
from emporio.llm import ChatClient
from emporio.metrics import TurnMetrics
from emporio.tools import Toolset


class TurnState(TypedDict):
    history: list[dict[str, Any]]  # what is sent before this turn, already compacted
    new: list[dict[str, Any]]  # messages produced in this turn
    records: list[ToolCallRecord]
    pending: list[dict[str, Any]]  # tool calls the model asked for and nobody ran yet
    reply: str | None  # set when the model answered in text
    model_calls: int
    rounds: int  # tool rounds already run


class GraphAgent:
    def __init__(
        self,
        client: ChatClient,
        toolset: Toolset,
        system_prompt: Callable[[], str],
        *,
        max_tool_rounds: int = 6,
        clock: Callable[[], float] = time.perf_counter,
        max_history_chars: int = MAX_HISTORY_CHARS,
    ) -> None:
        self._client = client
        self._toolset = toolset
        self._system_prompt = system_prompt
        self._max_tool_rounds = max_tool_rounds
        self._clock = clock
        self._max_history_chars = max_history_chars
        self._graph = self._build()

    def _build(self) -> Any:
        def call_model(state: TurnState) -> dict[str, Any]:
            # Rebuilt on every call so the date and the open/closed status are never stale.
            messages = [
                {"role": "system", "content": self._system_prompt()},
                *state["history"],
                *state["new"],
            ]
            assistant = self._client.chat(messages, self._toolset.schemas)
            update: dict[str, Any] = {"model_calls": state["model_calls"] + 1, "pending": []}
            calls = assistant.get("tool_calls")
            if not calls:
                # An empty answer is no answer: `reply` stays None and the turn ends in the fallback.
                update["reply"] = (assistant.get("content") or "").strip() or None
                return update
            update["pending"] = calls
            update["new"] = [
                *state["new"],
                {"role": "assistant", "content": assistant.get("content"), "tool_calls": calls},
            ]
            return update

        def run_tools(state: TurnState) -> dict[str, Any]:
            new = list(state["new"])
            records = list(state["records"])
            for call in state["pending"]:
                function = call["function"]
                result = self._toolset.call(function["name"], function["arguments"])
                records.append(ToolCallRecord(function["name"], function["arguments"], result))
                new.append({"role": "tool", "tool_call_id": call["id"], "content": result})
            return {"new": new, "records": records, "pending": [], "rounds": state["rounds"] + 1}

        def after_model(state: TurnState) -> str:
            return "run_tools" if state["pending"] else END

        def after_tools(state: TurnState) -> str:
            return "call_model" if state["rounds"] < self._max_tool_rounds else END

        graph = StateGraph(TurnState)
        graph.add_node("call_model", call_model)
        graph.add_node("run_tools", run_tools)
        graph.add_edge(START, "call_model")
        graph.add_conditional_edges("call_model", after_model, {"run_tools": "run_tools", END: END})
        graph.add_conditional_edges(
            "run_tools", after_tools, {"call_model": "call_model", END: END}
        )
        return graph.compile()

    def reply(self, history: Sequence[dict[str, Any]], user_text: str) -> AgentTurn:
        started = self._clock()
        usage_before = _usage(self._client)
        state = self._graph.invoke(
            {
                # Only what is sent is shortened; the caller keeps (and saves) the whole conversation.
                "history": compact_history(history, self._max_history_chars),
                "new": [{"role": "user", "content": user_text}],
                "records": [],
                "pending": [],
                "reply": None,
                "model_calls": 0,
                "rounds": 0,
            },
            {"recursion_limit": 2 * self._max_tool_rounds + 5},
        )
        text = state["reply"] or FALLBACK_REPLY
        usage_after = _usage(self._client)
        metrics = TurnMetrics(
            latency_ms=round((self._clock() - started) * 1000),
            model_calls=state["model_calls"],
            tool_calls=len(state["records"]),
            prompt_tokens=usage_after.get("prompt_tokens", 0)
            - usage_before.get("prompt_tokens", 0),
            completion_tokens=usage_after.get("completion_tokens", 0)
            - usage_before.get("completion_tokens", 0),
        )
        new = [*state["new"], {"role": "assistant", "content": text}]
        return AgentTurn(text, new, state["records"], metrics)
