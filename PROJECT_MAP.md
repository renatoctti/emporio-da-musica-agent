# PROJECT_MAP.md

> Project map written on 2026-10-31 at commit `9a46ea0`. It describes **this repository** so that
> anyone (human or AI assistant) can find the stack, structure and conventions without reading
> every file. Sections marked *decided, not yet implemented* record the stack chosen before the
> code exists; update them as the code lands.

## 0. Reading index by scope

> Read this section first, then only the sections your task needs.
> `grep -n '^## ' PROJECT_MAP.md` gives the line of each section.

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

> **Sections that do not apply here:** §5, §8, §10. Skip them.

## 1. Identity & purpose

- **Project:** emporio-da-musica-agent, a text-message customer-service agent for Empório da
  Música, a fictional musical-instrument store in Campo Grande/MS (Brazil).
- **Type:** CLI application (Python package with a console entry point).
- **Domain:** retail customer service: product catalog, prices, stock, promotions, order status,
  and store policies (returns, shipping, payment, warranty, opening hours).
- **Who uses it:** store customers chatting in Portuguese; evaluators of a technical challenge
  who run it locally.
- **Source of the requirements:** the challenge brief (not in the repo) and the store data in
  `data/`.

## 2. Stack & runtime

| Workspace | Language/runtime | Package manager | Source |
|---|---|---|---|
| — (single project) | Python >= 3.11 (developed on 3.13) | pip + venv, PEP 621 `pyproject.toml`, setuptools backend | `pyproject.toml` |

**Monorepo tool:** not applicable.

## 3. Key frameworks and libraries

| Category | Choice | Version/mode | Source |
|---|---|---|---|
| Agent approach | Native function calling with a hand-written agent loop; **no agent framework** | decided, not yet implemented | — |
| LLM client | `openai` SDK against any OpenAI-compatible endpoint (`LLM_BASE_URL`); default provider OpenRouter | `>=1.40` | `pyproject.toml`, `.env.example` |
| Data layer | `pandas` over the CSVs in `data/`, loaded and cleaned in memory at startup; no database | `>=2.2` | `pyproject.toml` |
| Policy retrieval | Store manual PDF split by numbered sections; a tool returns the requested sections | decided, not yet implemented | `data/políticas_da_loja.pdf` |
| Config | `python-dotenv` reading `.env` | `>=1.0` | `pyproject.toml` |
| Validation | ⚠️ OPEN: tool arguments are JSON from the LLM; pydantic ships with `openai` and may be used | — | — |
| Auth | Not applicable (local CLI) | — | — |
| Async jobs | Not applicable | — | — |
| Tests | `pytest`; command `python -m pytest -q` | `>=8.0` | `pyproject.toml` |
| Lint / format | `ruff` (line length 100, target py311); `ruff check .` and `ruff format .` | `>=0.6` | `pyproject.toml` |

## 4. Architecture and real structure

Current tree (`git ls-files`):

```
data/                      store data, kept exactly as delivered
  desafio_tecnico_ai_eng - {categories,customers,orders,order_items,products,promotions}.csv
  políticas_da_loja.pdf
src/emporio/
  __init__.py
  __main__.py              console entry point (`emporio` script, `python -m emporio`)
tests/
  test_smoke.py
pyproject.toml  .env.example  .gitignore  README.md  PROJECT_MAP.md
```

**Architectural pattern:** decided, not yet implemented. A small layered package: data loading
and cleaning → deterministic tools (pure functions returning JSON-serializable dicts) → agent
loop (LLM + tool dispatch) → CLI. Tools never call the LLM; the agent loop never reads CSVs.

| What to create | Where |
|---|---|
| Data loading and cleaning | `src/emporio/` (module per concern) |
| Agent tools | `src/emporio/` |
| Prompts / persona | `src/emporio/` |
| Tests | `tests/test_<module>.py` |
| Sample conversations | ⚠️ OPEN: folder name to be fixed by the spec that generates them |

**Forbidden dependencies:** tools and data modules must not import the LLM client.

**Shared contract between layers:** the tool schemas (JSON Schema for function calling) are the
contract between the agent loop and the tools.

## 5. Styles and design system

Not applicable: no frontend.

## 6. Tests

- **Naming/location:** separate tree, `tests/test_*.py` (`tests/test_smoke.py`).
- **Levels:** unit only so far. The LLM is never called in unit tests (fake client).
- **Command:** `python -m pytest -q`

## 7. Local environment

- **Setup:** `python -m venv .venv`, then `.venv\Scripts\activate` (Windows) or
  `source .venv/bin/activate`, then `pip install -e ".[dev]"`.
- **Run:** `emporio` or `python -m emporio`.
- **Local services:** none.
- **Seed data:** not applicable (data read from `data/`).
- **Environment variables:** `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` (see `.env.example`).

## 8. CI/CD and deploy

Not applicable: no CI pipeline and no deploy; the project runs locally.

## 9. Security and configuration

- **Secrets:** `.env` (git-ignored) holds the API key; `.env.example` lists the variables.
- **Customer data:** `data/customers.csv` holds personal data (name, phone, e-mail). The store
  manual (section 9) cites LGPD. ⚠️ OPEN: identity check before showing order data, to be fixed
  in the specs.

## 10. Observability and feature flags

Not applicable.

## 11. Code conventions

- **Language:** code, identifiers, comments, docs, specs and commits in English; everything the
  agent says to the customer in Brazilian Portuguese.
- **Style:** ruff defaults with line length 100. Other conventions are not established yet.

## 12. External integrations

| Service | Used for | Where |
|---|---|---|
| OpenRouter (default) or any OpenAI-compatible API | LLM chat completions with tool calling | decided, not yet implemented |

## 13. Workflow

- **Issue tracker:** none.
- **Branch/commit:** work on `main`, small commits with Conventional Commit prefixes
  (`chore:`, `feat:`, `test:`, `docs:`); no force-push (challenge rule). No co-author trailers.

## 14. Open

- ⚠️ OPEN: default OpenRouter model id (needs a cheap model with reliable tool calling; check
  the OpenRouter model list before fixing it).
- ⚠️ OPEN: pydantic for tool argument validation, or plain dict checks.
