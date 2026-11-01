# PROJECT_MAP.md

> Project map, updated on 2026-10-31 after the implementation. It describes **this repository** so
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
| §9 Security and configuration | Touches secrets, customer data or the LLM provider config. |
| §11 Code conventions | Writes new code. |
| §12 External integrations | Touches the LLM provider. |
| §13 Workflow | Commits, branches or opens a PR. |

> **Sections that do not apply here:** §5 (no frontend), §8 (no CI or deploy), §10 (no observability).

## 1. Identity & purpose

- **Project:** emporio-da-musica-agent, a text-message customer-service agent (Melô) for Empório da
  Música, a fictional musical-instrument store in Campo Grande/MS (Brazil).
- **Type:** CLI application (Python package with a console entry point).
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
| Policy retrieval | `pypdf` splits the manual PDF into its numbered sections; one tool returns the requested sections | `policies.py` |
| Storage | `sqlite3` (standard library): sessions, messages, handoff tickets | `db.py` |
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
  policies.py            manual sections
  session.py orders.py   per-conversation state; identity check, order tools
  hours.py returns.py handoff.py   opening hours; return eligibility; handoff tickets
  db.py                  SQLite repositories
  tools.py prompt.py llm.py agent.py   tool registry, system prompt, model client, loop
  cli.py __main__.py     command line
  evals/                 routing eval (cases, runner, command)
tests/                   pytest; fakes.py is the scripted fake model
samples/                 customer scripts and the generated transcripts
evals/results/           JSON reports of live eval runs
.specs/emporio-agent/    overview, plan, progress log and the 11 specs
```

**Pattern:** layers that only depend downward. `data.py` and the pure domain modules (`pricing`,
`catalog`, `policies`, `orders`, `returns`, `handoff`, `hours`) know nothing about the model;
`tools.py` wraps them as function-calling tools and injects what the model must not control;
`agent.py` runs the loop; `cli.py` is the only module that touches stdin and stdout.

**Forbidden dependencies:** domain modules must not import `llm.py` or `agent.py`; `agent.py` must
not read CSVs.

| What to create | Where |
|---|---|
| A new tool | A pure function in a domain module, then an entry in `tools.py` (schema, injected arguments) and `TOOL_NAMES` |
| A prompt rule | `prompt.py`, plus a marker phrase in `tests/test_prompt.py` |
| A routing scenario | `src/emporio/evals/cases.py` |
| A sample conversation | A script in `samples/scripts/`, then `emporio replay` |

## 6. Tests

- Separate tree, `tests/test_*.py`, about 300 tests; unit tests use the real `data/` and a scripted
  fake model, never a real LLM.
- Command: `python -m pytest -q`. The live eval is separate: `python -m emporio.evals`.

## 7. Local environment

`python -m venv .venv`, activate it, `pip install -e ".[dev]"`, copy `.env.example` to `.env`, set
`LLM_API_KEY`, run `emporio`. Variables: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`,
`EMPORIO_TODAY`, `EMPORIO_DATA_DIR`, `EMPORIO_DB_PATH`.

## 9. Security and configuration

- **Secrets:** `.env` is git-ignored; `.env.example` lists the variables.
- **Customer data:** `data/customers.csv` and the SQLite file (`var/`, git-ignored) hold personal
  data. Order data is shown only after the identity check in `orders.py`; no tool accepts a
  customer id or name.

## 11. Code conventions

- Code, comments, docs, specs and commits in English; the agent speaks the customer's language.
- Business conditions are returned as `{"error": {"code", "message"}}`; infrastructure errors raise.
- Money is rounded half-up through `results.round_brl`; dates in tool output are ISO strings.

## 12. External integrations

| Service | Used for | Where |
|---|---|---|
| OpenRouter (or any OpenAI-compatible API) | Chat completions with tool calling | `src/emporio/llm.py` |

## 13. Workflow

Work on `main`, small commits with Conventional Commit prefixes (`feat:`, `fix:`, `test:`,
`docs:`, `chore:`), one commit per spec; no force-push and no history rewrite.