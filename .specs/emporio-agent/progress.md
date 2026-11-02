# Empório da Música agent: implementation progress

> Updated in the same commit that finishes each spec.

**Last update:** 2026-11-02

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
| 10-routing-eval | 🟢 Done | 20 tests; live runs: claude-haiku-5.5 21/21, qwen3.7-flash 20/21 |
| 11-samples-readme | 🟢 Done | 21 structure tests; clean-venv install verified |
| 12-web-interface | 🟢 Done | 57 tests; manual pass in Chrome (desktop and a 390 px frame, both themes) |
| 13-policy-search | 🟢 Done | 34-question gold set; BM25 recall@3 0.85, embeddings 0.97, hybrid 0.97 |

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

### 2026-10-31: spec 10, live runs

- First run with `anthropic/claude-haiku-5.5`: 18/21 (about 150k input tokens, a couple of cents). Report kept in `evals/results/claude-haiku-5.5-run1.json`.
- E18 was a real failure: an English question was answered in Portuguese. Rule 1 of the prompt now ties the language to the customer's latest message.
- E06 and E21 were wrong test design, not agent errors: E06 pre-verified a customer the model could not know about (now the customer gives the order and e-mail in the conversation), and E21 forbade the words "em estoque" that the reply legitimately uses for the alternatives.
- The first sample transcript for installments showed the model working out the 10x limit itself instead of calling `get_product`; the prompt now says installments and the PIX price exist only there.
- Final runs with the final prompt: `claude-haiku-5.5` 21/21 (160k in, 7k out, about US$ 0.02) and `qwen/qwen3.7-flash` 20/21 (109k in, 10k out, about US$ 0.005); the cheaper model fails E18 (English question answered in Portuguese). Reports in `evals/results/`.
- The cases and the prompt were adjusted after seeing results, so these numbers are not a held-out measurement.
### 2026-10-31: spec 11, samples and README

- Five sample conversations generated with `emporio replay` (scripts in `samples/scripts`), each against a fresh database; transcripts and index in `samples/`.
- README written: quick start (verified in a clean virtual environment: install, `emporio --help`, 310 tests passing), configuration, commands, architecture, decisions with the alternatives rejected, data handling, prompt strategy, evaluation with both models and the history of the first run, assumptions A1 to A13, limitations, AI assistant usage, samples and layout.
- 21 structure tests over scripts, transcripts and the README, plus a guard that no document names the tools used to plan the work.

### 2026-11-01: spec 12, local web interface

- Added `conversation.py` (the agent setup the CLI and the page share), the `web/` package (`WebApp`, a standard-library server, and a page of plain HTML, CSS and JavaScript with no external request) and the `emporio web` command.
- 57 new tests (routes, state, the trace of each tool, validation, host and origin checks, a model failure, a real HTTP round trip, and the static files). No test calls a real model.
- Manual pass in Chrome: 1920 px in the light and the dark theme (system choice and the toggle), a real conversation with an identity check, an order lookup and a handoff, the test-data dialog, the store panel, and a 390 px frame for the phone layout and the drawer. The pass found and fixed four things the tests could not: buttons meant only for narrow screens showed on desktop (a CSS order problem), a doubled focus ring on the message field, icon-only buttons without an accessible name, and header chips that took three rows on a phone.
- Not verified: Firefox and Safari, a real phone, and automated browser tests (the JavaScript has no unit tests).
### 2026-11-01: spec 12, visual redesign of the page

- The first look (warm paper, serif headings, colored pill tags, rounded cards with shadows, an icon-only send button) read as machine-made. Three directions were drawn as a Claude Design canvas (A central de atendimento, B store brand, C technical panel) and the author picked A, adding that the drawings looked too close to the current page, so A was applied more decisively than drawn.
- Only styling and a few markup details changed, no component was removed: neutral white and one accent (the store's navy), system sans only, 1 px borders and small radii, no shadows. Tool kinds are a colored dot beside the name, the avatar is a plain circle, the brand is a wordmark with a line-art note, "Enviar" is a text button, the suggestions are rows instead of cards and the panel is a thin timeline.
- Contrast was computed for every text pair in both themes: the lowest is 5.04:1 (AA needs 4.5:1).
- Checked again in Chrome (desktop, both themes, a real conversation) and at 500 px; the screenshots in `docs/` were retaken.
### 2026-11-01: spec 12, collapsible panel

- Added at the author's request: the side panel can be collapsed and expanded at any width, with a button in the header and an X inside the panel. On a wide screen the choice is saved in the browser and the chat takes the whole width; under 900 px it stays a drawer that always starts closed, and the dimmed backdrop appears only there. Clicking the label under a reply opens the panel again. Escape closes the drawer only on a narrow screen.
- Written test-first (a static check that the controls are not narrow-only and the choice is stored), but that test only reads the files. The behavior was checked in Chrome by running the page: default open, collapse and reopen from both buttons, Escape ignored on a wide screen, the choice surviving a reload, and the label under a reply reopening the panel.
- A slip worth recording: a PowerShell array literal dropped one of my edits (the comma binds tighter than `+`), which left two variables undeclared in the page script and the static test still green. The page was caught in the browser, not by the suite; the JavaScript still has no unit tests.
### 2026-11-02: spec 13, policy search

- Added a ranked search over the manual: a new tool search_policies, backed by BM25 and, when an embeddings model is reachable, fused with cosine similarity over embeddings by reciprocal rank fusion. Embeddings are lazy, cached on disk by text hash under var/, and any failure falls back to BM25, so the project still runs offline and without a key.
- Added a gold set of 34 customer questions, written from the manual (7 of them vague on purpose), and a command: python -m emporio.evals.retrieval. Real run with openai/text-embedding-3-small through OpenRouter:

| Method | recall@1 | recall@3 | MRR |
|---|---|---|---|
| BM25 | 0.76 | 0.85 | 0.82 |
| Embeddings only | 0.88 | 0.97 | 0.93 |
| Hybrid | 0.79 | 0.97 | 0.88 |

- The hybrid ties the embeddings on recall@3 and is a little worse on the first position. I did not tune the fusion weight on this gold set, because that would only fit the test. The hybrid stays the default because BM25 protects exact terms (CNPJ, PAC, Sedex) that a vector can blur; this is a judgement, not something the 34 questions prove.
- Test first: tests/test_retrieval.py was written before the module. One expectation was wrong (BM25 only returns sections with a positive score, so a narrow query returns one hit, not two); the test was fixed, not the code. Ruff removed two unused noqa comments.
- Rule 3 of the prompt now tells the model to call search_policies when it does not know the section. The live agent evaluation has not been rerun for this change; it runs once, after the last change of this round.

---

## Decisions made during implementation

| Decision | Spec | Rationale |
|---|---|---|
| Hybrid search stays the default although embeddings alone scored slightly higher on this gold set | 13 | BM25 protects exact terms a vector can blur; 34 questions are too few to prove the difference, and tuning the weight on them would only fit the test. |
| The vector cache lives in var/ and is not committed | 13 | It is derived data and var/ is ignored; the evaluation result file in evals/results is what the repository keeps. |
| No external vector database | 13 | It would need an account and a key and break the offline run; the Embedder protocol is the seam where one would plug in. |
| The web session is created on first use instead of at startup | 12 | A server that fails to bind (port in use) leaves no empty session in the database. |
| `theme.js` is a separate file | 12 | The page sends a Content-Security-Policy without inline scripts, and the saved theme must still be applied before the first paint. |
| `/api/state` returns the turns of the current conversation | 12 | A page reload restores the transcript and the panel instead of showing an empty page over a live conversation. |
| A failed identity check counts as a failed step in the trace (`ok` false) | 12 | The result is not an error object, but the panel should show it as a refusal. |
| The page shows two fictional customers to try | 12 | An evaluator cannot guess a valid order and e-mail; both come from the provided data and the endpoint test checks that they pass the real identity check. |
| The README does not claim that the author reviewed every commit | 11 | The assistant cannot know it happened; the AI section describes the workflow and the mistakes found instead. | 
| The Spanish sample test checks intent (Spanish, mentions instruments, no tool call) instead of an exact word | 11 | The first version pinned a word from a model reply, which changes on every generation. |
| The transcripts were regenerated with a fresh database each | 11 | A reused database made sample 04 reuse an older ticket (duplicate detection working, but a confusing example). |
| `PROJECT_MAP.md` rewritten after the implementation | 11 | It still described the stack as decided but not built. |
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

### 2026-11-01: spec 12, visible way to open the panel

- Added at the author's request, because it was not clear that the Como decidiu button opens a side panel. The button now carries a side-panel icon whose right pane is filled while the panel is open and empty while it is collapsed, and it takes the accent color when collapsed. On a wide screen a collapsed panel also leaves a vertical tab on the right edge of the window, with an arrow, and the words Como decidiu; clicking it reopens the panel and moves focus into it.
- Test-first again, with the same limit: the new test only reads the files. Checked in Chrome in both themes: the tab and the icon states, the click on the tab, focus landing on the first tab of the panel, no console errors. The screenshots in docs/ were retaken because the header now shows the button.

### 2026-11-01: spec 12, counters removed

- Removed at the author's request: the numbers on the Como decidiu button (lookups) and on the Painel da loja tab (tickets), and the matching one on the collapsed tab. They read as unread notifications, which they are not. The header button keeps its side-panel icon.
