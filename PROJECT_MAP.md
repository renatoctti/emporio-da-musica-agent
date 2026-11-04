# PROJECT_MAP.md

> Project map, updated on 2026-11-03 after the third round (specs 22 to 24). It describes **this repository** so
> that anyone (human or AI assistant) can find the stack, structure and conventions without reading
> every file. The README has the user-facing documentation; this file is the contributor's view.

## 0. Reading index by scope

| Section | Read when the task... |
|---|---|
| §1 Identity & purpose | Always. |
| §2 Stack & runtime | Touches code. |
| §3 Key frameworks and libraries | Uses or changes a layer (data, LLM, tests). |
| §4 Architecture and real structure | Creates, moves or locates a file. |
| §6 Tests | Writes or runs a test. |
| §7 Local environment | Runs the project locally. |
| §8 CI and deploy | Touches the workflow or the Docker image. |
| §10 Observability | Reads or changes the per-turn metrics. |
| §9 Security and configuration | Touches secrets, customer data or the LLM provider config. |
| §11 Code conventions | Writes new code. |
| §12 External integrations | Touches the LLM provider. |
| §13 Workflow | Commits, branches or opens a PR. |

> **Section that does not apply here:** §5 (there is no frontend framework; the page is static files, see §3).

## 1. Identity & purpose

- **Project:** emporio-da-musica-agent, a text-message customer-service agent (Melô) for Empório da
  Música, a fictional musical-instrument store in Campo Grande/MS (Brazil).
- **Type:** CLI application (Python package with a console entry point), with a local web chat and an MCP server over stdio.
- **Domain:** retail customer service: catalog, prices, stock, promotions, order status, returns,
  store policies.
- **Who uses it:** store customers chatting in Portuguese (English and Spanish also handled) and
  the evaluators of a technical challenge running it locally.

## 2. Stack & runtime

| Workspace | Language/runtime | Package manager | Source |
|---|---|---|---|
| single project | Python >= 3.11 (developed on 3.13) | pip + venv, PEP 621 `pyproject.toml`, setuptools | `pyproject.toml` |

## 3. Key frameworks and libraries

| Category | Choice | Source |
|---|---|---|
| Agent approach | Native function calling with a hand-written loop; no agent framework | `src/emporio/agent.py` |
| LLM client | `openai` SDK against any OpenAI-compatible endpoint; OpenRouter and `anthropic/claude-haiku-5.5` by default | `llm.py`, `.env.example` |
| Data layer | `pandas` over the CSVs in `data/`, cleaned in memory at load; no database for the store data | `data.py` |
| Policy retrieval | `pypdf` splits the manual PDF into its numbered sections; one tool returns sections by id and another ranks them (BM25 fused with optional embeddings) | `policies.py`, `retrieval.py` |
| MCP server | The nine tools over stdio, JSON-RPC written by hand, no SDK | `mcp_server.py` |
| Metrics and context | Time, lookups and tokens per turn; a character budget for the history sent to the model | `metrics.py`, `context.py` |
| Storage | `sqlite3` (standard library): sessions, messages, handoff tickets, answer ratings | `db.py` |
| Web interface | Standard-library HTTP server and a static page (HTML, CSS, JavaScript); no framework, no build step, no external request | `web/` |
| Config | `python-dotenv` reading `.env` | `config.py` |
| Argument validation | Each tool's JSON schema is checked before the function runs; no pydantic | `tools.py` |
| Tests | `pytest` (`python -m pytest -q`) | `pyproject.toml` |
| Lint / format | `ruff check .` and `ruff format .` (line length 100, `.specs` excluded) | `pyproject.toml` |

## 4. Architecture and real structure

```
data/                    CSVs and the manual PDF, exactly as delivered
src/emporio/
  config.py results.py   settings; error result and money rounding helpers
  data.py                load and clean the CSVs, list data issues
  pricing.py catalog.py  price quote; product search and detail
  policies.py retrieval.py   manual sections; ranked search (BM25, optional embeddings)
  metrics.py context.py      per-turn measurements; history budget
  mcp_server.py          MCP server over stdio
  session.py orders.py   per-conversation state; identity check, order tools
  hours.py returns.py handoff.py   opening hours; return eligibility; handoff tickets
  webhook.py             optional webhook told about each new handoff ticket (HANDOFF_WEBHOOK_URL)
  db.py                  SQLite repositories
  tools.py prompt.py llm.py agent.py   tool registry, system prompt, model client, loop
  conversation.py        the agent for one session, shared by the CLI and the web page
  cli.py __main__.py     command line
  web/                   local web interface: app.py (routes), server.py, static/ (the page; cards.js draws the answer cards, loja.html is the demo store page)
  evals/                 evaluation: cases (routing and adversarial), runner, retrieval, command
tests/                   pytest; fakes.py is the scripted fake model
samples/                 customer scripts and the generated transcripts
evals/results/           JSON reports of live eval runs and of the policy search
.github/workflows/       CI: ruff, format check and pytest on 3.11 and 3.12, plus a Docker build
Dockerfile               image for the terminal chat
docs/                    screenshots of the web interface
.specs/emporio-agent/    overview, plan, progress log and the 24 specs
```

**Pattern:** layers that only depend downward. `data.py` and the pure domain modules (`pricing`,
`catalog`, `policies`, `orders`, `returns`, `handoff`, `hours`) know nothing about the model;
`tools.py` wraps them as function-calling tools and injects what the model must not control;
`agent.py` runs the loop; `cli.py` is the only module that touches stdin and stdout.

**Forbidden dependencies:** domain modules must not import `llm.py` or `agent.py`; `agent.py` must
not read CSVs; `mcp_server.py` only knows the `Toolset`.

| What to create | Where |
|---|---|
| A new tool | A pure function in a domain module, then an entry in `tools.py` (schema, injected arguments) and `TOOL_NAMES` |
| A prompt rule | `prompt.py`, plus a marker phrase in `tests/test_prompt.py` |
| A routing scenario | `src/emporio/evals/cases.py` |
| A sample conversation | A script in `samples/scripts/`, then `emporio replay` |
| A change to the page | `src/emporio/web/static/`; check both themes, the developer mode and a narrow width by hand, tests cannot judge the design |

## 6. Tests

- Separate tree, `tests/test_*.py`, about 520 tests; unit tests use the real `data/` and a scripted
  fake model, never a real LLM.
- Command: `python -m pytest -q`. The live eval is separate: `python -m emporio.evals`.

## 7. Local environment

`python -m venv .venv`, activate it, `pip install -e ".[dev]"`, copy `.env.example` to `.env`, set
`LLM_API_KEY`, run `emporio`. Variables: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`,
`EMPORIO_TODAY`, `EMPORIO_DATA_DIR`, `EMPORIO_DB_PATH`, `EMBEDDING_MODEL`, `EMPORIO_EMBEDDINGS`, `LLM_PRICE_IN_PER_M`, `LLM_PRICE_OUT_PER_M`, `HANDOFF_WEBHOOK_URL`.

## 8. CI and deploy

- `.github/workflows/ci.yml` runs `ruff check .`, `ruff format --check .` and `pytest -q` on Python 3.11
  and 3.12, and a `docker` job that builds the image and runs `data-report` and `stats`. Read-only
  permissions, no secret, only official actions.
- `Dockerfile`: python 3.12 slim, editable install from `/app`, non-root user, database in a
  `/data` volume, entrypoint `emporio`, default command `chat`. The key is passed at run time.

## 9. Security and configuration

- **Secrets:** `.env` is git-ignored; `.env.example` lists the variables.
- **Customer data:** `data/customers.csv` and the SQLite file (`var/`, git-ignored) hold personal
  data. Order data is shown only after the identity check in `orders.py`; no tool accepts a
  customer id or name. The web server listens on 127.0.0.1 and refuses other Host and Origin values.

## 10. Observability

- Every answer is measured (`metrics.py`): wall time, model calls, tool calls and tokens, stored in the
  `turn_metrics` table with the conversation. `emporio stats` and the Métricas tab of the web developer
  mode report them. The cost is shown only when `LLM_PRICE_IN_PER_M` and `LLM_PRICE_OUT_PER_M` are set.

## 11. Code conventions

- Code, comments, docs, specs and commits in English; the agent speaks the customer's language.
- Business conditions are returned as `{"error": {"code", "message"}}`; infrastructure errors raise.
- Money is rounded half-up through `results.round_brl`; dates in tool output are ISO strings.

## 12. External integrations

| Service | Used for | Where |
|---|---|---|
| OpenRouter (or any OpenAI-compatible API) | Chat completions with tool calling; optional embeddings for the manual search | `src/emporio/llm.py`, `retrieval.py` |

## 13. Workflow

Work on `main`, small commits with Conventional Commit prefixes (`feat:`, `fix:`, `test:`,
`docs:`, `chore:`), one commit per spec; no force-push and no history rewrite.