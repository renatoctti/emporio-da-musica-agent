# Spec 14: Per-turn metrics (latency, tokens, cost)

**Status:** 🟢 Implemented
**Author:** renatoctti
**Date:** 2026-11-02
**Scope:** measure every answer, store the numbers, report them in the CLI, the web page and the evaluation
**Depends on:** 05, 08, 09, 10, 12
**Delivery:** autonomous (after its dependencies)

---

## Summary

The agent reports nothing about what an answer costs. This spec measures, for every turn, the
time it took, how many model calls and tool calls it needed and how many tokens it used. The
numbers are stored with the conversation, shown by a new command (emporio stats), returned to the
web page and added to the evaluation report. Cost in dollars is only computed when the author
configures the model prices, because the project does not know them and must not invent them.

## Context

The challenge grades routing (data, policy or person), and an engineer running an assistant also
needs to watch latency and cost. The client already counts tokens in total (usage); this spec
reads that counter before and after a turn, so the fake clients used in the tests still work
(they have no usage and count as zero tokens).

---

## Allowed files

**Production**

- src/emporio/metrics.py (new): TurnMetrics, Prices, cost_usd, summarize, format_summary
- src/emporio/agent.py: measure the turn; AgentTurn.metrics
- src/emporio/config.py: price_in_per_m, price_out_per_m
- src/emporio/db.py: table turn_metrics; append_messages(metrics=...); load_turn_metrics
- src/emporio/cli.py: record metrics; the stats command
- src/emporio/web/app.py: metrics in the chat response and in the turns of the state
- src/emporio/evals/runner.py, src/emporio/evals/__main__.py: latency and tokens per case and in total

**Tests:** tests/test_metrics.py (new), tests/test_evals.py, tests/test_web.py

**Docs:** README.md, PROJECT_MAP.md, .env.example

---

## Functional requirements

| ID | Requirement | Priority | Acceptance |
|---|---|---|---|
| ✅ RF-01 | TurnMetrics holds latency_ms, model_calls, tool_calls, prompt_tokens, completion_tokens. cost_usd(metrics, prices) is None when a price is missing and tokens times price per million otherwise | Must | 1000 in at 1 USD and 500 out at 5 USD per million costs 0.0035 |
| ✅ RF-02 | Agent.reply measures the wall time of the turn with an injectable clock, counts model calls and tool calls, and takes the token difference of client.usage when the client has it | Must | Fake clock and fake usage |
| ✅ RF-03 | AgentTurn.metrics exists on every turn, including the fallback answer, with zeros when nothing was measured | Must | Fallback test |
| ✅ RF-04 | Settings read LLM_PRICE_IN_PER_M and LLM_PRICE_OUT_PER_M (USD per million tokens); blank means unknown; a non-number or a negative number is a ConfigError | Must | Config tests |
| ✅ RF-05 | append_messages accepts metrics and saves them in the same transaction as the messages; load_turn_metrics returns them by turn index; a database created before this spec gets the table on connect | Must | DB tests |
| ✅ RF-06 | emporio stats [--session ID] prints turns, latency (mean, median, p95), tokens, tool calls per turn and the estimated cost, or a line saying the prices are not configured | Must | CLI tests |
| ✅ RF-07 | The chat endpoint returns the metrics of the turn and the state returns them for every turn, so a page reload keeps them | Must | Web tests |
| ✅ RF-08 | The evaluation report has latency and tokens per case and the totals; the summary line prints the mean latency per case | Should | Eval tests |

## Non-functional requirements

- No new dependency. No price is written in the code.
- Metrics never contain message text.

## Out of scope

- Prices fetched from the provider and per-model price tables.
- Time per tool call and streaming latency.

## Test checklist

- [x] ✅ TurnMetrics, cost, summary
- [x] ✅ Agent measurement with a fake clock and fake usage
- [x] ✅ Settings, database, CLI, web, evaluation
