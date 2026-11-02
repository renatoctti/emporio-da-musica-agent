"""Spec 14: per-turn metrics (latency, model and tool calls, tokens, optional cost)."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

import pytest

from emporio import cli
from emporio.agent import Agent
from emporio.config import ConfigError, load_settings
from emporio.db import SessionStore, connect
from emporio.metrics import Prices, TurnMetrics, cost_usd, format_summary, summarize
from tests.fakes import FakeChatClient, assistant_calls, assistant_text, tool_call

NOW = datetime(2026, 3, 25, 10, 0)
TURN = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]


class UsageClient(FakeChatClient):
    """Fake model that adds 100 prompt and 20 completion tokens on every call."""

    def __init__(self, script, **kwargs):
        super().__init__(script, **kwargs)
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0}

    def chat(self, messages, tools):
        self.usage["prompt_tokens"] += 100
        self.usage["completion_tokens"] += 20
        return super().chat(messages, tools)


class StubToolset:
    def __init__(self):
        self.schemas = [{"type": "function", "function": {"name": "echo"}}]

    def call(self, name, arguments_json):
        return json.dumps({"echo": name})


def ticking(*values):
    sequence = iter(values)
    return lambda: next(sequence)


# --- RF-01 -------------------------------------------------------------------------------------


def test_cost_is_unknown_without_prices_and_exact_with_them():
    metrics = TurnMetrics(10, 1, 0, 1000, 500)
    assert cost_usd(metrics, Prices(None, None)) is None
    assert cost_usd(metrics, Prices(1.0, None)) is None
    assert cost_usd(metrics, Prices(1.0, 5.0)) == pytest.approx(0.0035)


def test_summary_statistics_and_report_lines():
    turns = [TurnMetrics(ms, 2, 1, 100, 10) for ms in (1000, 2000, 3000, 4000)]
    summary = summarize(turns, Prices(1.0, 5.0))
    assert summary.turns == 4
    assert summary.latency_mean_ms == 2500 and summary.latency_median_ms == 2500
    assert summary.latency_p95_ms == 4000
    assert summary.prompt_tokens == 400 and summary.completion_tokens == 40
    assert summary.tool_calls_per_turn == 1.0
    assert summary.cost_usd == pytest.approx(400 / 1e6 + 40 * 5 / 1e6)
    text = "\n".join(format_summary(summary))
    assert "4 turns" in text and "p95" in text and "USD" in text


def test_summary_without_prices_says_so_and_empty_input_is_safe():
    assert summarize([], Prices(None, None)).turns == 0
    text = "\n".join(format_summary(summarize([TurnMetrics(1, 1, 0, 1, 1)], Prices(None, None))))
    assert "not configured" in text


# --- RF-02 / RF-03 -----------------------------------------------------------------------------


def test_agent_measures_latency_calls_and_tokens():
    script = [assistant_calls(tool_call("c1", "echo", {})), assistant_text("pronto")]
    agent = Agent(UsageClient(script), StubToolset(), lambda: "SYS", clock=ticking(10.0, 10.42))
    turn = agent.reply([], "oi")
    assert turn.metrics == TurnMetrics(
        latency_ms=420, model_calls=2, tool_calls=1, prompt_tokens=200, completion_tokens=40
    )


def test_a_client_without_usage_counts_zero_tokens_and_the_fallback_has_metrics():
    agent = Agent(
        FakeChatClient([assistant_text(None)], repeat_last=True),
        StubToolset(),
        lambda: "SYS",
        clock=ticking(0.0, 0.1),
    )
    turn = agent.reply([], "oi")
    assert turn.metrics.prompt_tokens == 0 and turn.metrics.latency_ms == 100
    assert turn.metrics.model_calls == 1


# --- RF-04 -------------------------------------------------------------------------------------


def test_prices_come_from_the_environment_and_blank_means_unknown():
    env = {"EMPORIO_DB_PATH": ":memory:"}
    assert load_settings(env).price_in_per_m is None
    both = load_settings({**env, "LLM_PRICE_IN_PER_M": "1", "LLM_PRICE_OUT_PER_M": "5.5"})
    assert (both.price_in_per_m, both.price_out_per_m) == (1.0, 5.5)
    assert load_settings({**env, "LLM_PRICE_IN_PER_M": " "}).price_in_per_m is None


@pytest.mark.parametrize("bad", ["abc", "-1"])
def test_invalid_prices_are_a_config_error(bad):
    with pytest.raises(ConfigError):
        load_settings({"EMPORIO_DB_PATH": ":memory:", "LLM_PRICE_IN_PER_M": bad})


# --- RF-05 -------------------------------------------------------------------------------------


def _store():
    store = SessionStore(connect(":memory:"))
    return store, store.create_session("test/model", date(2026, 3, 25), NOW)


def test_metrics_are_stored_with_the_turn_and_indexed_by_turn():
    store, sid = _store()
    first = TurnMetrics(1500, 2, 1, 300, 40)
    second = TurnMetrics(900, 1, 0, 120, 15)
    store.append_messages(sid, TURN, NOW, first)
    store.append_messages(sid, TURN, NOW, second)
    store.append_messages(sid, TURN, NOW)  # no metrics: no row
    assert store.load_turn_metrics(sid) == {0: first, 1: second}
    assert len(store.load_messages(sid)) == 6


def test_an_old_database_gets_the_table_on_connect(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, model TEXT NOT NULL, reference_date TEXT)"
    )
    old.commit()
    old.close()
    conn = connect(path)
    assert conn.execute("SELECT COUNT(*) FROM turn_metrics").fetchone()[0] == 0


def test_all_turn_metrics_across_sessions_or_for_one():
    store, sid = _store()
    other = store.create_session("test/model", date(2026, 3, 25), NOW)
    store.append_messages(sid, TURN, NOW, TurnMetrics(1, 1, 0, 1, 1))
    store.append_messages(other, TURN, NOW, TurnMetrics(2, 1, 0, 1, 1))
    assert len(store.all_turn_metrics()) == 2
    assert [m.latency_ms for m in store.all_turn_metrics(other)] == [2]


# --- RF-06 -------------------------------------------------------------------------------------


def _run(argv, env):
    written: list[str] = []
    code = cli.main(argv, env=env, client_factory=lambda s: None, read=input, write=written.append)
    return code, "\n".join(written)


def test_stats_command_reports_stored_metrics(tmp_path):
    db = tmp_path / "var" / "e.db"
    env = {
        "EMPORIO_DB_PATH": str(db),
        "EMPORIO_TODAY": "2026-03-25",
        "LLM_PRICE_IN_PER_M": "1",
        "LLM_PRICE_OUT_PER_M": "5",
    }
    store = SessionStore(connect(db))
    sid = store.create_session("test/model", date(2026, 3, 25), NOW)
    store.append_messages(sid, TURN, NOW, TurnMetrics(2000, 2, 1, 1000, 200))
    code, out = _run(["stats"], env)
    assert code == 0 and "1 turns" in out and "USD" in out
    code, out = _run(["stats", "--session", sid], env)
    assert code == 0 and "1 turns" in out


def test_stats_without_data_and_with_an_unknown_session(tmp_path):
    env = {"EMPORIO_DB_PATH": str(tmp_path / "var" / "e.db"), "EMPORIO_TODAY": "2026-03-25"}
    code, out = _run(["stats"], env)
    assert code == 0 and "No metrics yet" in out
    assert _run(["stats", "--session", "nope"], env)[0] == 2
