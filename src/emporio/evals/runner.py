"""Runs eval cases against an agent and checks tools, reply text and price grounding."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from functools import lru_cache
from pathlib import Path

from emporio.agent import Agent, AgentTurn
from emporio.config import Settings
from emporio.data import StoreData, load_store_data
from emporio.db import HandoffStore, SessionStore, connect
from emporio.evals.cases import EvalCase
from emporio.llm import ChatClient
from emporio.policies import PolicySection, load_policy_sections, policy_index
from emporio.prompt import build_system_prompt
from emporio.retrieval import build_retriever
from emporio.session import SessionState
from emporio.tools import ToolContext, Toolset

POLICY_FILE = "políticas_da_loja.pdf"
PRICE_TOLERANCE_BRL = 0.005
_AMOUNT = re.compile(r"R\$\s*(\d+(?:\.\d{3})*(?:,\d{1,2})?)")
_JSON_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_BRAZILIAN_NUMBER = re.compile(r"\d+(?:\.\d{3})*(?:,\d+)?")


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    passed: bool
    failures: list[str]
    replies: list[str]
    tool_names: list[str]
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


def _brazilian_number(text: str) -> float:
    return float(text.replace(".", "").replace(",", "."))


def parse_amounts(text: str) -> list[tuple[str, float]]:
    """Every `R$ <amount>` in the text, as (the text as written, the value)."""
    return [(m.group(0), _brazilian_number(m.group(1))) for m in _AMOUNT.finditer(text)]


def _json_numbers(text: str) -> list[float]:
    """Numbers in tool results, which are JSON with a dot as the decimal separator."""
    return [float(match) for match in _JSON_NUMBER.findall(text)]


def _brazilian_numbers(text: str) -> list[float]:
    """Numbers the customer wrote: `1000`, `1.000` or `1.000,50`."""
    return [_brazilian_number(match) for match in _BRAZILIAN_NUMBER.findall(text)]


def grounded_prices(reply: str, tool_results: Sequence[str], user_text: str) -> list[str]:
    """Amounts in the reply that no tool result and no customer message contains."""
    known = [n for text in tool_results for n in _json_numbers(text)]
    known += _brazilian_numbers(user_text)
    return [
        written
        for written, value in parse_amounts(reply)
        if not any(abs(value - n) <= PRICE_TOLERANCE_BRL for n in known)
    ]


def evaluate_case(case: EvalCase, turns: Sequence[AgentTurn]) -> CaseResult:
    tool_names = [call.name for turn in turns for call in turn.tool_calls]
    replies = [turn.reply for turn in turns]
    failures: list[str] = []

    if case.expect_tools_any and not set(case.expect_tools_any) & set(tool_names):
        failures.append(
            f"expected one of the tools {list(case.expect_tools_any)}, got {tool_names}"
        )
    for name in dict.fromkeys(tool_names):
        if name in case.forbid_tools:
            failures.append(f"forbidden tool called: {name}")
    if case.reply_must_match_any and not any(
        re.search(p, replies[-1], re.IGNORECASE) for p in case.reply_must_match_any
    ):
        failures.append(f"final reply matches none of {list(case.reply_must_match_any)}")
    for pattern in case.reply_must_not_match:
        if any(re.search(pattern, reply, re.IGNORECASE) for reply in replies):
            failures.append(f"a reply matches the forbidden pattern {pattern!r}")

    results_so_far: list[str] = []
    user_text_so_far: list[str] = []
    for turn in turns:
        results_so_far.extend(call.result for call in turn.tool_calls)
        user_text_so_far.extend(m["content"] for m in turn.new_messages if m["role"] == "user")
        for amount in grounded_prices(turn.reply, results_so_far, " ".join(user_text_so_far)):
            failures.append(f"price {amount} did not come from a tool result")

    return CaseResult(
        case.id,
        not failures,
        failures,
        replies,
        tool_names,
        latency_ms=sum(turn.metrics.latency_ms for turn in turns),
        prompt_tokens=sum(turn.metrics.prompt_tokens for turn in turns),
        completion_tokens=sum(turn.metrics.completion_tokens for turn in turns),
    )


@lru_cache(maxsize=2)
def _knowledge(data_dir: Path) -> tuple[StoreData, tuple[PolicySection, ...]]:
    return load_store_data(data_dir), load_policy_sections(data_dir / POLICY_FILE)


def run_case(case: EvalCase, client: ChatClient, settings: Settings) -> CaseResult:
    data, policies = _knowledge(settings.data_dir)
    today = date.fromisoformat(case.today)
    now = datetime.combine(today, time(10, 0))
    index = policy_index(policies)

    conn = connect(":memory:")  # never the real database
    try:
        session_id = SessionStore(conn).create_session(settings.llm_model, today, now)
        state = SessionState(verified_customer_id=case.verified_as)
        retriever = build_retriever(settings, policies)
        context = ToolContext(data, policies, state, HandoffStore(conn), session_id, now, retriever)
        agent = Agent(client, Toolset(context), lambda: build_system_prompt(now, index))
        history: list[dict] = []
        turns: list[AgentTurn] = []
        for message in case.messages:
            turn = agent.reply(history, message)
            history.extend(turn.new_messages)
            turns.append(turn)
    finally:
        conn.close()
    return evaluate_case(case, turns)


def with_model(settings: Settings, model: str | None) -> Settings:
    return replace(settings, llm_model=model) if model else settings
