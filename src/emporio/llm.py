"""Thin client for any OpenAI-compatible chat endpoint (OpenRouter by default)."""

from __future__ import annotations

from typing import Any, Protocol

from openai import OpenAI

from emporio.config import Settings

TEMPERATURE = 0.2
TIMEOUT_SECONDS = 60.0
MAX_RETRIES = 2


class MissingApiKeyError(RuntimeError):
    """LLM_API_KEY is not set."""


class ChatClient(Protocol):
    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        """Return the assistant message; it has no `tool_calls` key when there are none."""


class OpenAIChatClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.llm_api_key:
            raise MissingApiKeyError("Set LLM_API_KEY (see .env.example)")
        self._client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=TIMEOUT_SECONDS,
            max_retries=MAX_RETRIES,
        )
        self._model = settings.llm_model
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0}

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        response = self._client.chat.completions.create(
            model=self._model, messages=messages, tools=tools, temperature=TEMPERATURE
        )
        if response.usage is not None:
            self.usage["prompt_tokens"] += response.usage.prompt_tokens
            self.usage["completion_tokens"] += response.usage.completion_tokens
        message = response.choices[0].message
        result: dict[str, Any] = {"role": "assistant", "content": message.content}
        if message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
                for call in message.tool_calls
            ]
        return result
