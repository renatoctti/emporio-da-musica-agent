import json

import pytest

from emporio.agent import FALLBACK_REPLY, Agent
from emporio.config import load_settings
from emporio.llm import MissingApiKeyError, OpenAIChatClient
from tests.fakes import FakeChatClient, assistant_calls, assistant_text, tool_call

SCHEMAS = [{"type": "function", "function": {"name": "echo"}}]


class StubToolset:
    schemas = SCHEMAS

    def __init__(self):
        self.calls = []

    def call(self, name, arguments_json):
        self.calls.append((name, arguments_json))
        return json.dumps({"echo": name})


def make_agent(script, *, rounds=6, repeat_last=False):
    client = FakeChatClient(script, repeat_last=repeat_last)
    toolset = StubToolset()
    agent = Agent(client, toolset, lambda: "SYSTEM", max_tool_rounds=rounds)
    return agent, client, toolset


def test_a_plain_answer_has_two_new_messages():
    agent, client, _ = make_agent([assistant_text("Oi! Sou a Melô.")])
    turn = agent.reply([], "Oi")
    assert turn.reply == "Oi! Sou a Melô."
    assert turn.new_messages == [
        {"role": "user", "content": "Oi"},
        {"role": "assistant", "content": "Oi! Sou a Melô."},
    ]
    assert turn.tool_calls == []
    messages, tools = client.calls[0]
    assert messages[0] == {"role": "system", "content": "SYSTEM"} and tools == SCHEMAS


def test_two_tool_rounds_then_text():
    script = [
        assistant_calls(tool_call("c1", "a", {})),
        assistant_calls(tool_call("c2", "b", {"x": 1})),
        assistant_text("Pronto."),
    ]
    agent, client, toolset = make_agent(script)
    turn = agent.reply([], "pergunta")
    assert turn.reply == "Pronto."
    assert [m["role"] for m in turn.new_messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
    ]
    assert turn.new_messages[2] == {
        "role": "tool",
        "tool_call_id": "c1",
        "content": '{"echo": "a"}',
    }
    assert [(r.name, r.result) for r in turn.tool_calls] == [
        ("a", '{"echo": "a"}'),
        ("b", '{"echo": "b"}'),
    ]
    assert turn.tool_calls[1].arguments == '{"x": 1}'
    assert len(client.calls) == 3
    assert [m["role"] for m in client.calls[2][0]] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
    ]
    assert toolset.calls == [("a", "{}"), ("b", '{"x": 1}')]


def test_several_calls_in_one_assistant_message_all_run_in_order():
    script = [
        assistant_calls(tool_call("c1", "a", {}), tool_call("c2", "b", {})),
        assistant_text("Feito."),
    ]
    agent, _, toolset = make_agent(script)
    turn = agent.reply([], "x")
    assert [m["role"] for m in turn.new_messages] == [
        "user",
        "assistant",
        "tool",
        "tool",
        "assistant",
    ]
    assert [m["tool_call_id"] for m in turn.new_messages if m["role"] == "tool"] == ["c1", "c2"]
    assert [c[0] for c in toolset.calls] == ["a", "b"]


def test_persisted_messages_rebuild_the_same_request_on_the_next_turn():
    script = [
        assistant_calls(tool_call("c1", "a", {})),
        assistant_text("um"),
        assistant_text("dois"),
    ]
    agent, client, _ = make_agent(script)
    first = agent.reply([], "primeira")
    agent.reply(first.new_messages, "segunda")
    sent = client.calls[-1][0]
    assert sent == [
        {"role": "system", "content": "SYSTEM"},
        *first.new_messages,
        {"role": "user", "content": "segunda"},
    ]
    assert not any(m["role"] == "system" for m in first.new_messages)


def test_the_round_limit_ends_with_the_fallback_reply():
    agent, client, _ = make_agent(
        [assistant_calls(tool_call("c", "a", {}))], rounds=6, repeat_last=True
    )
    turn = agent.reply([], "x")
    assert len(client.calls) == 6
    assert turn.reply == FALLBACK_REPLY
    assert turn.new_messages[-1] == {"role": "assistant", "content": FALLBACK_REPLY}
    assert len(turn.tool_calls) == 6


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_empty_content_without_tool_calls_is_the_fallback(empty):
    agent, _, _ = make_agent([assistant_text(empty)])
    turn = agent.reply([], "x")
    assert turn.reply == FALLBACK_REPLY
    assert turn.new_messages[-1]["content"] == FALLBACK_REPLY


def test_system_prompt_is_rebuilt_on_every_call():
    texts = iter(["um", "dois"])
    client = FakeChatClient([assistant_text("a"), assistant_text("b")])
    agent = Agent(client, StubToolset(), lambda: next(texts))
    agent.reply([], "1")
    agent.reply([], "2")
    assert [c[0][0]["content"] for c in client.calls] == ["um", "dois"]


def test_missing_api_key_fails_at_construction():
    settings = load_settings({})
    assert settings.llm_api_key is None
    with pytest.raises(MissingApiKeyError, match="LLM_API_KEY"):
        OpenAIChatClient(settings)


def test_client_with_a_key_builds_without_network():
    settings = load_settings({"LLM_API_KEY": "test-key", "LLM_MODEL": "some/model"})
    client = OpenAIChatClient(settings)
    assert client.usage == {"prompt_tokens": 0, "completion_tokens": 0}
