"""One conversation: the agent, its tools and the per-session state, shared by the CLI and the web."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from emporio.agent import Agent, AgentTurn
from emporio.config import Settings
from emporio.data import StoreData
from emporio.db import HandoffStore
from emporio.llm import ChatClient
from emporio.policies import PolicySection, policy_index
from emporio.prompt import build_system_prompt
from emporio.retrieval import build_retriever
from emporio.session import SessionState
from emporio.tools import ToolContext, Toolset


@dataclass
class Conversation:
    session_id: str
    state: SessionState
    reply: Callable[[list[dict[str, Any]], str], AgentTurn]


def start_conversation(
    settings: Settings,
    client: ChatClient,
    data: StoreData,
    policies: tuple[PolicySection, ...],
    handoffs: HandoffStore,
    session_id: str,
) -> Conversation:
    state = SessionState()
    retriever = build_retriever(settings, policies)
    context = ToolContext(data, policies, state, handoffs, session_id, settings.now, retriever)
    index = policy_index(policies)
    agent = Agent(client, Toolset(context), lambda: build_system_prompt(settings.now, index))
    return Conversation(session_id, state, agent.reply)
