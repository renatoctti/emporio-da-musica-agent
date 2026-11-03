"""Spec 19: the history sent to the model stays within a character budget."""

from __future__ import annotations

import copy
import json

from emporio.agent import Agent
from emporio.context import OMITTED_RESULT, compact_history
from tests.fakes import FakeChatClient, assistant_text


class StubToolset:
    def __init__(self):
        self.schemas = []

    def call(self, name, arguments_json):
        return "{}"


def turn(n: int, size: int = 100) -> list[dict]:
    """A customer message, a tool call with a result of the given size, and the final answer."""
    call_id = f"c{n}"
    function = {"name": "get_product", "arguments": "{}"}
    return [
        {"role": "user", "content": f"pergunta {n}"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": call_id, "type": "function", "function": function}],
        },
        {"role": "tool", "tool_call_id": call_id, "content": json.dumps({"data": "x" * size})},
        {"role": "assistant", "content": f"resposta {n}"},
    ]


def history(turns: int, size: int = 100) -> list[dict]:
    return [message for n in range(turns) for message in turn(n, size)]


def tool_messages(messages):
    return [m for m in messages if m["role"] == "tool"]


# --- RF-01 -------------------------------------------------------------------------------------


def test_a_history_within_the_budget_is_unchanged_but_is_a_new_list():
    original = history(3)
    result = compact_history(original, max_chars=100_000)
    assert result == original and result is not original


# --- RF-02 -------------------------------------------------------------------------------------


def test_old_tool_results_become_a_note_and_the_last_two_turns_stay_intact():
    original = history(5, size=2_000)
    result = compact_history(original, max_chars=10_000)
    assert len(result) == len(original)
    results = tool_messages(result)
    assert [m["content"] for m in results[:3]] == [OMITTED_RESULT] * 3
    assert results[3:] == tool_messages(original)[3:]
    # every call is still answered by a tool message with the same id
    ids = [m["tool_call_id"] for m in tool_messages(original)]
    assert [m["tool_call_id"] for m in results] == ids
    assert json.loads(OMITTED_RESULT)["omitted"] is True


# --- RF-03 -------------------------------------------------------------------------------------


def test_if_the_budget_is_still_exceeded_the_oldest_turns_are_dropped_whole():
    original = history(12, size=500)
    result = compact_history(original, max_chars=3_000)
    assert result[0]["role"] == "user"
    assert result[-8:] == original[-8:]  # the last two turns are intact
    assert len(result) < len(original)
    # no orphan: every tool message follows an assistant message that asked for it
    asked = {c["id"] for m in result if m.get("tool_calls") for c in m["tool_calls"]}
    assert {m["tool_call_id"] for m in tool_messages(result)} <= asked


def test_the_last_two_turns_are_kept_even_when_they_alone_exceed_the_budget():
    original = history(6, size=5_000)
    result = compact_history(original, max_chars=1_000)
    assert result == original[-8:]
    assert result[0]["role"] == "user"


# --- RF-04 -------------------------------------------------------------------------------------


def test_the_input_is_not_modified_and_the_result_is_deterministic():
    original = history(8, size=2_000)
    snapshot = copy.deepcopy(original)
    first = compact_history(original, max_chars=6_000)
    second = compact_history(original, max_chars=6_000)
    assert original == snapshot
    assert first == second


# --- RF-05 -------------------------------------------------------------------------------------


def test_the_agent_sends_the_compacted_history_and_the_caller_keeps_the_full_one():
    client = FakeChatClient([assistant_text("ok")])
    agent = Agent(client, StubToolset(), lambda: "SYS", max_history_chars=6_000)
    full = history(8, size=2_000)
    snapshot = copy.deepcopy(full)
    reply = agent.reply(full, "nova pergunta")
    sent = client.calls[0][0]
    assert sent[0] == {"role": "system", "content": "SYS"}
    assert sent[-1] == {"role": "user", "content": "nova pergunta"}
    assert any(m.get("content") == OMITTED_RESULT for m in sent)
    assert full == snapshot  # what the caller saves is untouched
    assert reply.reply == "ok"
