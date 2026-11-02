"""Per-turn measurements: time, model and tool calls, tokens, and an optional cost.

The project does not know what a model costs and must not invent it, so the cost is only
computed when the author sets the prices (LLM_PRICE_IN_PER_M and LLM_PRICE_OUT_PER_M, in USD per
million tokens). Latency and tokens are always available.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TurnMetrics:
    latency_ms: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class Prices:
    in_per_m: float | None
    out_per_m: float | None


def cost_usd(metrics: TurnMetrics, prices: Prices) -> float | None:
    if prices.in_per_m is None or prices.out_per_m is None:
        return None
    return (
        metrics.prompt_tokens * prices.in_per_m + metrics.completion_tokens * prices.out_per_m
    ) / 1_000_000


def as_dict(metrics: TurnMetrics, prices: Prices) -> dict[str, Any]:
    """The turn as the web page receives it."""
    return {
        "latency_ms": metrics.latency_ms,
        "model_calls": metrics.model_calls,
        "tool_calls": metrics.tool_calls,
        "prompt_tokens": metrics.prompt_tokens,
        "completion_tokens": metrics.completion_tokens,
        "cost_usd": cost_usd(metrics, prices),
    }


@dataclass(frozen=True)
class Summary:
    turns: int
    latency_mean_ms: float
    latency_median_ms: float
    latency_p95_ms: float
    prompt_tokens: int
    completion_tokens: int
    tool_calls_per_turn: float
    cost_usd: float | None


def summarize(turns: Sequence[TurnMetrics], prices: Prices) -> Summary:
    if not turns:
        return Summary(0, 0.0, 0.0, 0.0, 0, 0, 0.0, None)
    latencies = sorted(t.latency_ms for t in turns)
    p95_index = max(0, math.ceil(0.95 * len(latencies)) - 1)  # nearest-rank percentile
    prompt = sum(t.prompt_tokens for t in turns)
    completion = sum(t.completion_tokens for t in turns)
    return Summary(
        turns=len(turns),
        latency_mean_ms=statistics.fmean(latencies),
        latency_median_ms=statistics.median(latencies),
        latency_p95_ms=latencies[p95_index],
        prompt_tokens=prompt,
        completion_tokens=completion,
        tool_calls_per_turn=sum(t.tool_calls for t in turns) / len(turns),
        cost_usd=cost_usd(TurnMetrics(0, 0, 0, prompt, completion), prices),
    )


def format_summary(summary: Summary) -> list[str]:
    lines = [
        f"{summary.turns} turns, {summary.tool_calls_per_turn:.1f} tool calls per turn",
        (
            f"latency: mean {summary.latency_mean_ms:.0f} ms, "
            f"median {summary.latency_median_ms:.0f} ms, p95 {summary.latency_p95_ms:.0f} ms"
        ),
        f"tokens: {summary.prompt_tokens} in, {summary.completion_tokens} out",
    ]
    if summary.cost_usd is None:
        lines.append(
            "estimated cost: not configured (set LLM_PRICE_IN_PER_M and LLM_PRICE_OUT_PER_M)"
        )
    else:
        lines.append(f"estimated cost: {summary.cost_usd:.4f} USD")
    return lines
