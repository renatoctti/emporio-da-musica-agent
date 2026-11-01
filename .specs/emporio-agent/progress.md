# Empório da Música agent: implementation progress

> Updated in the same commit that finishes each spec.

**Last update:** 2026-10-31

---

## Overall status

| Spec | Status | Notes |
|---|---|---|
| 01-foundation-data | 🟢 Done | 21 tests, ruff clean |
| 02-pricing | 🟢 Done | 30 tests |
| 03-catalog | 🟢 Done | 23 tests |
| 04-policy-retrieval | 🟢 Done | 14 tests |
| 05-persistence | 🟢 Done | 13 tests |
| 06-customer-orders | 🟢 Done | 26 tests |
| 07-returns-handoff | 🟢 Done | 59 tests |
| 08-agent-loop | 🟢 Done | 51 tests |
| 09-cli | 🟢 Done | 28 tests |
| 10-routing-eval | 🟡 Code done, live run pending | 19 tests; needs LLM_API_KEY for the live run |
| 11-samples-readme | 🔴 Not started | |

> Legend: 🔴 not started · 🟡 in progress · 🟢 done · ❌ blocked

---

## Implementation log

### 2026-10-31: spec 01, foundation and data

- Added `config.py` (settings, `ConfigError`), `results.py` (error helper, half-up rounding) and `data.py` (typed tables, cleaning, issue report).
- 19 new tests; the full suite has 21 passing.
- The unreliable-description rule found exactly the expected ids {135, 137, 139, 140, 142, 144} on the real data, so no divergence from the spec.

### 2026-10-31: spec 02, price quote

- Added `pricing.py`: promotion, PIX (only without promotion) and installment options by the item 3.1 tiers.
- 30 new tests (boundaries at 100, 150, 320 and 700 reais; contiguity of options).
- Decimal arithmetic is done exactly and rounded once through `results.round_brl`.

### 2026-10-31: spec 03, catalog search and product detail

- Added `catalog.py`: `search_products` (name, category, price, string type, electroacoustic filters) and `get_product` (price quote, expired promotions, alternatives).
- 23 new tests on the real data; a named product is found even when unavailable, plain listings only show products in stock.
- Price filters use the current (promotional) price.

### 2026-10-31: spec 04, policy retrieval

- Added `policies.py`: the manual is parsed with pypdf (layout mode) into the 28 numbered sections; page headers and footers are dropped, table rows are joined with pipes, and the two contradictions (WhatsApp number and e-mail accent) are corrected after extraction.
- Heading detection accepts top-level ids only in increasing order, so the numbered list of item 7.2 is not mistaken for sections.
- `get_policy_sections` expands a top-level id to its subsections and reports unknown ids.
- Added `pypdf` to the dependencies.

### 2026-10-31: spec 05, persistence

- Added `db.py`: SQLite connection with the schema created on connect, `SessionStore` (messages stored as JSON in OpenAI format) and `HandoffStore` (protocol built from the row id in the same transaction).
- 13 new tests, including reconnecting to the same file, foreign keys with rollback and ticket protocol numbering.

### 2026-10-31: spec 06, customer verification and orders

- Added `session.py` (`SessionState`) and `orders.py`: `verify_customer`, `get_order_status`, `list_my_orders` and the shared `require_owned_order`.
- Verification compares the e-mail or phone with the customer who owns the order (the e-mail shared by customers 11 and 43 never crosses orders); wrong contact and unknown order give identical answers; three failures lock the session.
- 26 new tests on the real data.

### 2026-10-31: spec 07, business hours, returns and handoff

- Added `hours.py` (opening hours and business-hour arithmetic), `returns.py` (`check_return_eligibility`: regret and preference 7 days from receipt, defect exchange 30 days from purchase, then legal warranty 90 days from receipt, then manufacturer warranty) and `handoff.py` (`open_handoff` with a protocol and a 24 business-hour deadline).
- 59 new tests, including Saturday, Sunday and out-of-hours arithmetic and every window boundary.
- An open ticket for the same order and category is reused instead of duplicated.

### 2026-10-31: spec 08, agent loop

- Added `tools.py` (eight tools with JSON schemas, argument validation and injected context), `prompt.py` (Melô persona, store facts, current date and open/closed status, 13 rules, policy index), `llm.py` (OpenAI-compatible client) and `agent.py` (the loop).
- 51 new tests with a scripted fake model; no test calls a real LLM.
- The model cannot override the session, the data or the clock: injected values win and unexpected arguments are rejected.

### 2026-10-31: spec 09, command-line interface

- Added `cli.py`: `chat` (new or `--resume`), `sessions`, `handoffs`, `export`, `replay` and `data-report`; `emporio` alone starts a chat.
- The verification state is not restored on resume and the CLI says so; a missing API key exits with code 1 before any session is created.
- Transcripts show each tool call and a truncated result, so the data lookups are visible in the samples.
- 28 new tests with injected I/O and a fake model, plus 3 for the persistence extensions.

### 2026-10-31: spec 10, routing eval (code)

- Added `evals/`: 21 scenarios (catalog, price rules, returns, orders, privacy, scope, language, handoff), a price-grounding check that every R$ amount in a reply appears in a tool result or in the customer's message, and the `python -m emporio.evals` command with a JSON report.
- 19 new tests with a scripted model. The live run against a real model is still pending (no API key yet).

---

## Decisions made during implementation

| Decision | Spec | Rationale |
|---|---|---|
| Case E08 expects `get_order_status` instead of both `verify_customer` and `get_order_status` | 10 | `expect_tools_any` means at least one; the order tool refuses to answer without a verification, so calling it implies the verification happened. |
| Number parsing is split: tool results are read as JSON (dot decimal), customer text as Brazilian format | 10 | A single pattern read 439.2 as 439; a unit test caught it. |
| `python -m emporio.evals` lives in `evals/__main__.py` | 10 | That is the file Python runs for `-m`; the spec listed it as the command line module. |
| Added `SessionStore.append_messages` (one transaction per turn) and `SessionStore.get_session`; `SessionInfo` gained an optional `reference_date` | 09 | A turn has several messages and a failure halfway would leave a history the API rejects on resume; the export header needs the model and reference date. These three tests in `test_db.py` were written together with the code, not before it. |
| `main` accepts keyword-only `env`, `client_factory`, `read` and `write` | 09 | Lets the tests run the real command parsing with a fake model and injected I/O. |
| An invalid `--today` exits with code 2 and `replay` of a missing script exits with code 2 | 09 | Both are user input errors, like an unknown session id. |
| `__main__.py` switches stdout and stderr to UTF-8 | 09 | The Windows console default code page garbles Portuguese accents. |
| Corrected the acceptance count of RF-08 from 5 to 6 new messages | 08 | Two tool rounds plus the final answer is user, assistant, tool, assistant, tool, assistant. |
| The prompt has 13 rules instead of 12 | 08 | Added an explicit rule for out-of-stock, discontinued and coming-soon products (manual item 7.3). |
| `OpenAIChatClient` keeps a `usage` counter and tool arguments sent as null are treated as omitted | 08 | The eval reports token use; models often send null for optional arguments. |
| `tests/__init__.py` added so tests can import `tests.fakes` | 08 | Shared fake client for the agent, CLI and eval tests. |
| Exposed `require_owned_order(data, state, order_id)` from `orders.py` | 06 | Spec 07 needs the same ownership rule; reusing it avoids a second copy of the check that decides who may see an order. |
