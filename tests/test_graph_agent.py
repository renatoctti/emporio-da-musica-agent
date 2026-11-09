"""The graph version must behave exactly like the hand-written loop, for the same scripted model."""

import json

import pytest

from emporio.agent import FALLBACK_REPLY, Agent
from emporio.graph_agent import GraphAgent
from tests.fakes import FakeChatClient, assistant_calls, assistant_text, tool_call

SCHEMAS = [{"type": "function", "function": {"name": "echo"}}]


class StubToolset:
    schemas = SCHEMAS

    def __init__(self):
        self.calls = []

    def call(self, name, arguments_json):
        self.calls.append((name, arguments_json))
        return json.dumps({"echo": name})


def run(agent_class, script, *, history=(), rounds=6, repeat_last=False):
    client = FakeChatClient(script, repeat_last=repeat_last)
    toolset = StubToolset()
    ticks = iter(range(0, 10_000, 5))  # a clock that advances 5 ms per reading
    agent = agent_class(
        client,
        toolset,
        lambda: "SYSTEM",
        max_tool_rounds=rounds,
        clock=lambda: next(ticks) / 1000,
    )
    turn = agent.reply(list(history), "pergunta")
    return turn, client.calls, toolset.calls


SCRIPTS = {
    "plain answer": ([assistant_text("Oi! Sou a Melô.")], {}),
    "two tool rounds then text": (
        [
            assistant_calls(tool_call("c1", "a", {})),
            assistant_calls(tool_call("c2", "b", {"x": 1})),
            assistant_text("Pronto."),
        ],
        {},
    ),
    "several calls in one message": (
        [
            assistant_calls(tool_call("c1", "a", {}), tool_call("c2", "b", {}), content="vou ver"),
            assistant_text("Feito."),
        ],
        {},
    ),
    "round limit ends in the fallback": (
        [assistant_calls(tool_call("c1", "a", {}))],
        {"repeat_last": True, "rounds": 3},
    ),
    "empty answer is the fallback": ([assistant_text("   ")], {}),
    "none content is the fallback": ([assistant_text(None)], {}),
    "history is sent before the new messages": (
        [assistant_text("Certo.")],
        {"history": [{"role": "user", "content": "antes"}, {"role": "assistant", "content": "ok"}]},
    ),
}


@pytest.mark.parametrize("name", list(SCRIPTS))
def test_the_graph_makes_the_same_turn_as_the_loop(name):
    script, options = SCRIPTS[name]
    loop = run(Agent, script, **options)
    graph = run(GraphAgent, script, **options)
    assert graph[0].reply == loop[0].reply
    assert graph[0].new_messages == loop[0].new_messages
    assert graph[0].tool_calls == loop[0].tool_calls
    assert graph[0].metrics.model_calls == loop[0].metrics.model_calls
    assert graph[0].metrics.tool_calls == loop[0].metrics.tool_calls
    assert graph[1] == loop[1]  # the model saw exactly the same requests
    assert graph[2] == loop[2]  # and the tools ran with the same arguments


def test_the_fallback_is_what_both_return_at_the_round_limit():
    script, options = SCRIPTS["round limit ends in the fallback"]
    turn, calls, _ = run(GraphAgent, script, **options)
    assert turn.reply == FALLBACK_REPLY
    assert len(calls) == 3  # one model call per round, then it stops


def test_a_new_turn_builds_a_fresh_state():
    client = FakeChatClient([assistant_text("um"), assistant_text("dois")])
    agent = GraphAgent(client, StubToolset(), lambda: "SYSTEM")
    first = agent.reply([], "a")
    second = agent.reply(first.new_messages, "b")
    assert [m["role"] for m in second.new_messages] == ["user", "assistant"]
    assert [m["role"] for m in client.calls[1][0]] == ["system", "user", "assistant", "user"]


def test_the_evaluation_runner_can_drive_the_graph_with_the_real_tools():
    from emporio.config import load_settings
    from emporio.evals.cases import EvalCase
    from emporio.evals.runner import run_case

    client = FakeChatClient(
        [
            assistant_calls(tool_call("c1", "get_product", {"product_id": 95})),
            assistant_text("O Takamine GD20 custa R$ 2.199,00."),
        ]
    )
    case = EvalCase(
        "T1",
        ("Quanto custa o Takamine GD20?",),
        expect_tools_any=("get_product",),
        reply_must_match_any=(r"2\.199",),
    )
    settings = load_settings({"EMPORIO_TODAY": "2026-03-25"})
    result = run_case(case, client, settings, GraphAgent)
    assert result.passed and result.tool_names == ["get_product"]
