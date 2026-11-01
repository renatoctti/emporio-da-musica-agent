# Empório da Música: virtual assistant

## Overview

**Melô** is a text-message customer-service agent for Empório da Música, a fictional musical
instrument store in Campo Grande/MS. It answers the recurring questions (opening hours, product
price and availability, order status, returns, shipping, payment) in the store's voice, and it
decides on every message whether to look something up in the store **data**, look it up in the
store **policy manual**, open a **human handoff ticket**, or politely decline an out-of-scope
request.

It is a Python project built for a technical challenge. The agent is a plain function-calling
loop around eight tools; everything that has to be exactly right (prices, installments, return
deadlines, who may see an order) is computed by code, not by the model.

- Product search and detail with promotions, PIX discount and installment options.
- Policy answers that cite the manual item ("item 4.1"), read from the PDF.
- Order status behind an identity check (order number plus the e-mail or phone on that order).
- Return and warranty eligibility from the order dates, and handoff tickets with a protocol and a
  response deadline counted in store opening hours.
- Replies in the customer's language (Portuguese, English or Spanish were exercised).
- Conversations are saved in SQLite and can be resumed or exported as Markdown.
- A local web interface (`emporio web`) with light and dark themes and a panel that shows, for every reply, which lookups the agent made.

## Quick start

Requirements: Python 3.11 or newer and an API key for an OpenAI-compatible chat endpoint
(OpenRouter by default).

```bash
git clone https://github.com/renatoctti/emporio-da-musica-agent.git
cd emporio-da-musica-agent
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env             # Windows: copy .env.example .env
# edit .env and set LLM_API_KEY
emporio                          # or: python -m emporio
emporio web                      # the same agent in the browser, http://127.0.0.1:8765
python -m pytest -q              # about 370 tests, no API key needed
```

The sample data ends in March 2026, so for realistic dates (delivery estimates, return windows)
pretend it is still then: `emporio --today 2026-03-25`.

**Provider.** The default is OpenRouter with `anthropic/claude-haiku-5.5`. Any endpoint that speaks
the OpenAI chat API with tool calling can be used through `LLM_BASE_URL` and `LLM_MODEL`; only
OpenRouter was tested. The model must support tool calling.

## Configuration

Set in `.env` (see `.env.example`) or in the environment. Blank values count as unset.

| Variable | Default | Meaning |
|---|---|---|
| `LLM_API_KEY` | none | API key. Without it the CLI exits with code 1 before creating a session. |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-compatible endpoint. |
| `LLM_MODEL` | `anthropic/claude-haiku-5.5` | Model id. |
| `EMPORIO_TODAY` | system clock | Fixes "today" as `YYYY-MM-DD` (at 10:00). `--today` does the same per run. |
| `EMPORIO_DATA_DIR` | `data/` | Folder with the CSVs and the manual PDF. |
| `EMPORIO_DB_PATH` | `var/emporio.db` | SQLite file (git-ignored: it holds personal data). |

## Commands

| Command | What it does |
|---|---|
| `emporio` or `emporio chat` | Talk to Melô. Type `sair`, `exit` or `quit` (or Ctrl-C) to leave; the session id is printed. |
| `emporio chat --resume ID` | Continue a stored conversation. The identity check is **not** restored: the customer confirms the order again. |
| `emporio chat --verbose` | Print every tool call and a truncated result to stderr. |
| `emporio web [--port N] [--today D] [--no-browser]` | Open the chat in the browser, local only. See [Web interface](#web-interface). |
| `emporio sessions` | List stored conversations. |
| `emporio handoffs` | List open handoff tickets (what the store team would see). |
| `emporio export ID [-o FILE]` | Render a conversation as Markdown, with the tool calls. |
| `emporio replay SCRIPT [--today D] [-o FILE]` | Run a text file of customer messages through the agent and write the transcript. This is how the samples were made. |
| `emporio data-report` | List the problems found in the CSV files and how many. |
| `python -m emporio.evals [--model M] [--case ID] [--report FILE]` | Run the routing eval against a real model. |

### Web interface

`emporio web` opens the same agent in the browser at `http://127.0.0.1:8765`. Next to every reply,
a panel shows which lookups the agent made (catalog and order data, the manual, the identity check,
the return rules, a human handoff) with the arguments and the result of each one, so you can see
**when it chose data, when it chose policy and when it handed over to a person**. A second tab
shows the handoff tickets as the store team would see them, and a dialog offers two fictional
customers from the provided data to try the identity check.

![The web interface in the light theme](docs/web-interface-light.jpg)

![The web interface in the dark theme](docs/web-interface-dark.jpg)

- A system, light and dark theme control, remembered in the browser. Both themes are designed
  separately and the text keeps AA contrast in each.
- On a phone-sized screen the panel becomes a drawer.
- No external request and no extra dependency: a standard-library server and a page of plain HTML,
  CSS and JavaScript, so it also works offline.
- It listens on `127.0.0.1` only and refuses requests whose host or origin is not local, because it
  uses your API key and shows personal data. Replies are inserted as text, never as HTML.
- For a return inside the 7-day window run `emporio web --today 2026-02-19` and use customer 7
  from "Dados de teste".

## Architecture
```
customer text
   -> CLI (cli.py) or web page (web/)       history and tickets in SQLite (db.py)
   -> Agent loop (agent.py)  <->  LLM client (llm.py, OpenAI-compatible)
        | tool calls (JSON schemas, validated)
        v
   Toolset (tools.py)  injects data, verification state, clock and session id
        |-- catalog.py + pricing.py     products, promotions, PIX, installments
        |-- policies.py                 manual sections from the PDF
        |-- orders.py + session.py      identity check, order status
        |-- returns.py + handoff.py     eligibility, tickets
        |   (hours.py: opening hours)
        v
   data.py: CSVs loaded once into typed tables, cleaned, with a list of data issues
```

Rules that keep it honest:

- Tools never import the LLM client, and the agent loop never reads the CSVs.
- The CLI and the web page build the agent the same way (`conversation.py`).
- Business conditions (not found, not verified, invalid argument) are returned to the model as
  `{"error": {"code", "message"}}`. Infrastructure failures (disk, SQLite, network) raise.
- The model sends only the arguments in each tool's schema. The data, the verification state,
  the clock and the session id are injected by the code, so the model cannot override them.
- The system prompt is rebuilt on every call (date, open or closed) and is never stored in the
  history.

## Decisions and why

| Decision | Choice | Why, and what was rejected |
|---|---|---|
| Agent approach | Function calling with a hand-written loop (a short function in `agent.py`), no framework | Every step is visible and testable with a scripted fake model, and there are no framework dependencies. Rejected: LangChain-style frameworks (hidden control flow for a problem that is one loop), a free-form SQL agent (the model would write queries over personal data, and the data has traps a query would not know about), pure RAG over the tables (prices and stock must be exact, not retrieved by similarity). |
| Data access | Eight fixed tools over pandas tables | Results are exact and unit-testable; the model never sees a whole table (at most 10 products per search), which also protects customer data (the manual cites LGPD, item 9). |
| Business rules | In code, not in the prompt | Prices, PIX, installment limits (`pricing.py`), return windows (`returns.py`), business-hour deadlines (`hours.py`) and ownership checks (`orders.py`) are tested functions. A model only has to choose the tool and write the answer. The eval below tests exactly that claim. |
| Policies | The PDF is split into its 28 numbered sections; the section index is in the system prompt and one tool returns the requested sections | The manual is short and well structured, so section lookup is exact, cheap and lets the agent cite "item 4.1". Embeddings would add a dependency and fuzziness without a gain at this size. I would revisit it for a manual of tens of pages or for vague queries (BM25 plus embeddings). |
| Model and provider | OpenAI-compatible client, OpenRouter, `anthropic/claude-haiku-5.5` | Reliable tool calling and good Brazilian Portuguese at about US$ 0.10 per million input tokens (OpenRouter listing, 2026-10-31); one code path serves other providers. A cheaper model was compared (see Evaluation). |
| Interface | CLI, plus `export` and `replay` | The challenge asks for the agent, not a UI. `replay` makes the sample conversations reproducible instead of hand-written. |
| Web interface | A small page served with the standard library, with a panel that shows the lookups behind every reply | The challenge grades when the agent chooses data, policy or a person, and that is easier to judge when each lookup sits next to its answer. No framework, no build step and no external request, so it adds no dependency and works offline. It answers only local requests because it spends an API key and shows personal data. |
| Persistence | SQLite (standard library) for messages, sessions and tickets | A customer can resume a conversation and the store team can list tickets, with no server and no extra dependency. Each turn is saved in one transaction so a resumed history is always valid. |
| Identity | Order number plus the e-mail or phone registered on that order, checked in code | Order numbers are guessable and names are not secret. A wrong contact and an unknown order give the same answer, and three failures lock the session. |
| Handoff | A simulated ticket in SQLite with protocol `EMP-YYYYMMDD-NNNN` | Item 7.3 of the manual asks for "register and forward, answer in 24 business hours". There is no real queue to call, so the ticket is stored and listed by `emporio handoffs`. |
| Dependencies | `openai`, `pandas`, `pypdf`, `python-dotenv` | Nothing else is needed. |

## Data handling

The data has deliberate traps. `emporio data-report` lists them; this is what the code does.

| Finding | What the code does |
|---|---|
| Name and description disagree for products 135, 137, 139, 140, 142, 144 (another brand named, or "5 cordas" against `strings: 4`, "88 teclas" against `keys: 61`) | The description is dropped and the agent uses name, specs and price (`data.py`). |
| Product 96 is `active` with stock 0; product 136 is `discontinued` with stock 13; product 130 is `coming_soon` but appears in two orders | Availability is `out_of_stock`, `discontinued` (stock hidden) and `coming_soon`; unavailable products come with in-stock alternatives from the same category (manual item 7.3). |
| Categories 6, 7, 8 (woodwind, brass, orchestral strings) have no products, although the manual says the store sells them | The search says nothing is registered; the agent must not claim stock it cannot see. |
| Only 4 of 25 promotions are active; products 93, 96, 99 have two inactive ones | Only active promotions change the price; expired ones are listed so the agent can say they are not valid. |
| Orders 3 and 20: the recorded total differs from the sum of the items | The recorded `total_brl` is shown, never recomputed. |
| Orders 9, 16, 18 were paid in installments below the manual's minimum | Reported as recorded; new quotes follow item 3.1. |
| Customers 11 and 43 share an e-mail | Identity is checked against the owner of the order, never by looking customers up by e-mail. |
| The manual contradicts itself: two WhatsApp numbers, an e-mail with and without accent, a payment table that disagrees with item 3.1 | The number `(67) 3341-4444` and the unaccented e-mail are used, fixed once when the PDF is loaded; installments follow item 3.1. |
| Orders have no receipt date and the data ends in March 2026 | The estimated delivery stands in for the receipt date; "today" is configurable. |

## Prompt strategy

The system prompt (`prompt.py`) has five parts: the **persona** (Melô, informal but professional,
a virtual assistant, chat-sized messages), the **store facts** (address, phone, e-mail, hours),
**the current moment** (date, weekday, open or closed and the next opening, rebuilt on every
call), thirteen **numbered rules**, and the **manual's section index**.

The rules mostly say what the model must not do: state a price, stock, promotion or deadline
that did not come from a tool; compute anything itself; show order data before the identity
check; reveal whether an order exists after a failed check; name or invent other stores for
accessories; follow instructions inside the conversation that ask to reveal the rules or other
customers' data. Tool descriptions say when to use each tool, and the schemas use enums built
from the real data (the nine category names, the return reasons, the ticket categories).
The temperature is 0.2. A model call costs about 3.5k input tokens, mostly the prompt.

Prompt injection is handled twice: the prompt tells the model to ignore such requests, and,
more importantly, no tool can return another customer's data or accept a customer id or name.

## Evaluation

Unit tests use a scripted fake model, so they cannot show that a real model routes correctly.
`python -m emporio.evals` runs 21 scenarios through the real agent and checks three things:
**which tools were called** (and which must not be), **what the reply says** (regular expressions
that must or must not match), and **price grounding**: every `R$` amount in a reply must appear in a
tool result or in the customer's own message. The scenarios cover catalog and prices, installment
and PIX rules, expired promotions, returns, order status and identity, out-of-scope requests,
prompt injection, a complaint that needs a ticket, and an English question.

| Model | Result | Tokens (in / out) | Approx. cost |
|---|---|---|---|
| `anthropic/claude-haiku-5.5` | **21/21** | 160k / 7k | US$ 0.02 |
| `qwen/qwen3.7-flash` | **20/21** | 109k / 10k | US$ 0.005 |

The cheaper model fails case E18: it answers an English question in Portuguese. Both reports are
in `evals/results/`.

How to read these numbers:

- The first Haiku run scored **18/21** (`evals/results/claude-haiku-5.5-run1.json`). One failure
  was real (E18: the agent answered in Portuguese, so the language rule in the prompt was
  tightened). The other two were mistakes in my test design: E06 pre-verified a customer the model
  could not know about, and E21 forbade words the correct answer uses for the alternatives.
- The sample transcripts also changed the prompt: the first version of sample 02 showed the model
  working out the installment limit itself, so the prompt now says installments and the PIX price
  exist only in `get_product`.
- The scenarios and the prompt were therefore adjusted after seeing results. The table is a
  regression check, not a held-out measurement. Each model was run once, the model is not
  deterministic, and 21 scenarios are few. Prices are from the OpenRouter listing of 2026-10-31.

## Assumptions

The challenge says to document the assumptions that fill gaps in the material.

| ID | Assumption |
|---|---|
| A1 | The receipt date of a delivered order is its `estimated_delivery` (no real delivery date exists). |
| A2 | Every delivered order was an online purchase, so the 7-day regret right (item 4.1) applies. |
| A3 | "Today" is `EMPORIO_TODAY` when set, otherwise the system clock; the data ends in March 2026. |
| A4 | Manual contradictions: WhatsApp `(67) 3341-4444`, e-mail without accent, installment rules from item 3.1. |
| A5 | Order totals are shown as recorded (`total_brl`), even where they differ from the item sum. |
| A6 | Status meanings: `pending` awaiting payment confirmation, `confirmed` paid and being prepared, `shipped` on its way, `delivered`, `cancelled` (reason in notes). |
| A7 | Business hours follow item 2 (Mon-Fri 09-18, Sat 09-13, Sun closed); holidays are ignored. |
| A8 | Item 3.1 "up to 3x, except below R$ 50" is read as a R$ 50 minimum installment for 2x and 3x. |
| A9 | A discontinued product is treated as discontinued even when stock is above zero. |
| A10 | A description that contradicts its product name or specs is dropped; name, specs and price are used instead. |
| A11 | Categories without products are reported as having nothing registered; the agent does not claim to sell them. |
| A12 | Identity is checked against the e-mail or phone of the customer who owns the order (an e-mail is shared by customers 11 and 43). |
| A13 | Human handoff is simulated locally: a ticket in SQLite, listed by `emporio handoffs`. |

## Limitations and next steps

Known limits:

- **Search is lexical.** Words are matched against name, brand, category and description; there is
  no typo tolerance or synonym handling beyond the category enum the model picks from.
- **The description check is a heuristic.** It catches the six mismatches above (brand named or a
  contradicting count); it does not catch product 136's description ("Contrabaixo Precision" for a
  product named Ibanez), so other bad descriptions may slip through.
- **No shipping calculator.** The manual says freight depends on ZIP, weight and size, and none
  of those are in the data, so the agent only applies the policy.
- **Business hours ignore holidays** and the store is a single location.
- **The handoff is simulated.** No one is notified and tickets cannot be closed from the CLI.
- **Identity is a light check.** Whoever knows an order number and its e-mail or phone gets the
  data. The three-attempt lock is per session, so restarting the CLI resets it.
- **History and tickets are stored unencrypted** in `var/` and the whole history is sent on every
  turn (no summarising), so very long conversations grow in cost.
- **Prompt-injection defence is best effort.** The real barrier is that no tool exposes other
  customers' data.
- **The model can still slip in wording.** For example, sample 05 says "violón", which in Spanish
  is a double bass, for a Brazilian "violão".
- **The eval is small and was tuned** (see Evaluation); it has no multi-turn adversarial cases.
- **Not connected to WhatsApp**; there is no streaming and no latency work.
- **The web page is for one person on one machine.** It holds one conversation at a time, answers only local requests and is not meant to be exposed to a network. It was checked by hand in Chrome (desktop width and a 390 px frame, both themes), not in Firefox or Safari, and its JavaScript has no automated tests.

With more time I would: add a hybrid (BM25 plus embeddings) lookup for the manual, connect the
handoff to a real queue, add a holiday calendar and a freight API by ZIP code, rate-limit and log
identity attempts globally, encrypt the database and set a retention period, summarise long
conversations, and grow the eval (several seeds, an LLM judge for tone, multi-turn attacks).

## AI coding assistants

I used **Claude** through **Claude Code** to build this project, with a spec-driven workflow:

1. **Decisions first.** Before any code I went through a structured interview with Claude about
   the problem: the traps in the data, how to verify a customer, how return deadlines work, how
   to persist conversations, the persona. I made the decisions; the questions and my answers
   shaped the specs.
2. **Specs in the repository.** The outcome is in [`.specs/emporio-agent/`](.specs/emporio-agent/):
   an overview with the contracts read from the real files and the assumptions, an implementation
   order, 11 specs (each with requirements, contracts, edge cases and the tests to write) and a
   progress log with the decisions taken while implementing.
3. **One capability, one commit, test-first.** Each spec was implemented by writing the tests,
   seeing them fail, then writing the code, and committed on its own, so the history reads one
   capability at a time. The exception is noted in the progress log: three persistence tests
   were written together with the code.
4. **Running against a real model.** Claude drafted the code and the specs from my decisions; the
   live eval and the sample replays then found problems that unit tests could not (the language
   slip, the model computing installments itself), which led to prompt changes. The web interface followed the same path (spec 12, tests first) and its design was checked in a browser, because tests cannot say whether a page reads well.

Claude also made mistakes along the way, and the tests caught them: wrong numbers in a spec's
acceptance criteria, a price parser that read `439.2` as `439`, and two eval cases that were
badly designed. The progress log records each one.

The agent itself runs on a Claude model (Haiku) through OpenRouter, and a second model was used
for the comparison above.

## Sample conversations

Five conversations generated by the real agent with `emporio replay` (index and details in
[`samples/README.md`](samples/README.md)):

| Sample | What it shows |
|---|---|
| [samples/01-catalog.md](samples/01-catalog.md) | Search with a price filter and availability |
| [samples/02-price-installments.md](samples/02-price-installments.md) | Promotion, installment limit, PIX that does not stack |
| [samples/03-order-status.md](samples/03-order-status.md) | Identity check, order status, a late delivery and a ticket |
| [samples/04-return.md](samples/04-return.md) | **Non-trivial:** a regret return with eligibility rules, the manual cited and a ticket |
| [samples/05-out-of-scope-es.md](samples/05-out-of-scope-es.md) | Out-of-scope request in Spanish, no invented stores |

## Repository layout

```
data/                    the CSVs and the manual PDF, exactly as delivered
src/emporio/             the package (see Architecture); web/ is the browser interface, evals/ the routing eval
tests/                   about 370 tests; tests/fakes.py is the scripted fake model
samples/                 scripts (customer lines) and the generated transcripts
docs/                    screenshots of the web interface
evals/results/           JSON reports of the live eval runs
.specs/emporio-agent/    overview, plan, progress log and the 11 specs
PROJECT_MAP.md           stack and conventions at a glance
```