# Empório da Música agent: high-level description

**Status:** Draft
**Author:** renatoctti
**Date:** 2026-10-31
**Branch:** main

---

## Objective

A Python text-message customer-service agent for Empório da Música, a fictional musical-instrument
store in Campo Grande/MS. It answers recurring customer questions (opening hours, order status,
product price and availability, returns, shipping, payment) with a store persona, deciding on each
message whether to look up **data** (CSV tables), look up **policies** (the store manual PDF),
open a **human handoff**, or politely refuse an out-of-scope request.

Primary users: store customers chatting in Portuguese (sometimes English or Spanish). Secondary:
the store team, who see the handoff tickets the agent opens.

## Expected behavior (whole feature)

- The agent introduces itself as **Melô**, the store's virtual assistant, in an informal but
  professional tone (manual item 7.1), at most one emoji per message, always in the customer's
  language.
- It never states a price, stock level or deadline it did not get from a tool in the current
  conversation (manual item 7.1, "accurate information").
- Product questions go to deterministic catalog tools. Prices, promotions, PIX discount and
  installments are computed in code, never by the model.
- Policy questions go to a tool that returns numbered sections of the manual; the agent answers
  from that text and can cite the item number.
- Order data is shown only after the customer proves ownership (order number plus the e-mail or
  phone registered on that order). Verification state lives in code, per session.
- Return requests are checked by a deterministic eligibility tool; eligible and complaint cases
  open a handoff ticket with a protocol number and a "24 business hours" deadline.
- Conversations persist in SQLite and can be resumed; a transcript can be exported to Markdown.
- Out-of-scope requests (accessories, unrelated topics) are declined briefly and redirected,
  without inventing partner stores.

## Non-goals

- No shipping calculator (manual says freight depends on ZIP, weight and size; none are in the data).
- No real order placement, payment or stock reservation.
- No holiday calendar for business hours (only Sunday is treated as closed).
- No multi-user or web interface; CLI only.
- No vector store or embeddings (the manual has 28 numbered sections).

---

## Contracts and schemas

Read from the real files in `data/` (UTF-8 CSV, header row, `desafio_tecnico_ai_eng - <name>.csv`).

### products (65 rows)

`product_id` int, `price_brl` float, `name` str, `category_id` int, `description` str,
`stock_quantity` int, `status` `active|discontinued|coming_soon`, `specs` JSON string
(object, keys vary by category), `created_at` ISO date.

Known edge cases (verified by script on 2026-10-31):
- `status`: 62 active, 2 discontinued (113 with stock 0, **136 with stock 13**), 1 coming_soon (130, and it appears in orders 3 and 14).
- Stock 0 while `active`: product 96.
- Only categories 1, 2, 3, 4, 5 and 9 have products; **categories 6, 7, 8 (woodwind, brass, orchestral strings) have none**, although the manual lists them.
- Name and description disagree for ids 135, 137, 139, 140, 142, 144 (description names a different brand or contradicts `specs`, for example "5 cordas" against `strings: "4"`, "88 teclas" against `keys: "61"`).
- Specs keys: violões and ukuleles use `top`, `back_sides`, `neck`, `strings`, `scale`, `electronics`, `color`; electric guitars `body`, `neck`, `strings`, `color`; basses `body`, `neck`, `strings`, `color`; drums `shells`, `pieces`, `hardware`, `color`; keyboards `keys`, `type`, `polyphony`, `color`. For violões and ukuleles `strings` is `nylon|steel` and `electronics` is `yes|no`.

### categories (9), customers (50), orders (20), order_items (22), promotions (25)

- categories: `category_id`, `name`, `description`.
- customers: `customer_id`, `name`, `phone` (always `(DD) 9XXXX-XXXX`), `email`, `city`. **Customers 11 and 43 share `bruno.martins@jmail.com`.** Only customers 1 to 18 have orders.
- orders: `order_id`, `customer_id`, `order_date`, `status` (`delivered` 7, `confirmed` 4, `pending` 4, `cancelled` 4, `shipped` 1), `total_brl`, `payment_method` (`pix`, `debit`, `boleto`, `credit_3x|6x|12x`), `tracking_code` (only orders 1 to 8, format `BR` + 9 alphanumerics + `BR`), `estimated_delivery` (same orders), `notes` (only cancelled orders).
- order_items: `order_id`, `quantity`, `product_id` (22 rows, all products exist).
- promotions: `promotion_id`, `product_id`, `discount_percent`, `description`, `is_active` (0/1). **Only 4 are active**: 12 (product 127, 10%), 14 (121, 20%), 19 (90, 18%), 24 (94, 8%). Products 93, 96 and 99 have two inactive promotions each.
- Orders 3 and 20: `total_brl` differs from the sum of item prices (3450 against 3498; 1400 against 1488).
- Orders 9, 16 and 18 were paid in installments below the manual's minimum (item 3.1); the agent only reports what is recorded.

### Store manual (`data/políticas_da_loja.pdf`)

8 pages, 10 numbered sections and 18 subsections (28 in total). Contradictions: WhatsApp `(67) 3341-4444` (cover, item 1.2) against `(67) 3321-4500` (item 7); e-mail with and without accent; the payment table says credit card "parcela mínima R$ 100" while item 3.1 has tiered minimums.

---

## Feature architecture

| Layer | Artifact | Path | Spec |
|---|---|---|---|
| Config | settings, error helper | `src/emporio/config.py`, `results.py` | 01 |
| Data | loading and cleaning | `src/emporio/data.py` | 01 |
| Domain | price quote | `src/emporio/pricing.py` | 02 |
| Domain | catalog tools | `src/emporio/catalog.py` | 03 |
| Domain | policy sections | `src/emporio/policies.py` | 04 |
| Storage | SQLite sessions and handoffs | `src/emporio/db.py` | 05 |
| Domain | verification and orders | `src/emporio/session.py`, `orders.py` | 06 |
| Domain | hours, returns, handoff | `src/emporio/hours.py`, `returns.py`, `handoff.py` | 07 |
| Agent | tools registry, prompt, loop, LLM client | `src/emporio/tools.py`, `prompt.py`, `agent.py`, `llm.py` | 08 |
| Interface | CLI | `src/emporio/cli.py` | 09 |
| Quality | routing eval | `src/emporio/evals/` | 10 |
| Docs | samples and README | `samples/`, `README.md` | 11 |

### End-to-end flow

```
customer text → CLI → Agent.reply → LLM (tools schema)
   → tool call(s) → Toolset.call → catalog | policies | orders | returns | handoff (pure functions
     over StoreData and SessionState; SQLite only for handoffs and history)
   → JSON result back to the LLM → final text in the customer's language → CLI + SQLite history
Business errors come back as {"error": {"code", "message"}}; infrastructure errors propagate.
```

### Cross-cutting conventions

- Tool functions are plain functions returning JSON-serializable dicts. Business conditions
  (not found, not verified, invalid argument) are **returned** as `{"error": {"code", "message"}}`;
  I/O, SQLite and LLM failures **raise**.
- Money is `float` rounded half-up to 2 decimals via `results.round_brl`; dates are ISO strings in outputs.
- Error codes: `invalid_argument`, `unknown_category`, `product_not_found`, `not_verified`, `verification_locked`, `order_not_found`, `unknown_tool`.
- Tools never import the LLM client; the agent loop never reads CSVs.
- Code, comments, docs, specs and commits in English; the agent speaks Portuguese (or the customer's language).

---

## Dependencies and reuse

Nothing to reuse (greenfield). New external dependencies: `openai` (client for any
OpenAI-compatible endpoint), `pandas` (CSV loading and filtering), `python-dotenv`, `pypdf`
(manual text extraction; added in spec 04). SQLite comes with Python.

## Assumptions register (to be copied into the README)

| ID | Assumption |
|---|---|
| A1 | The receipt date of a delivered order is its `estimated_delivery` (no real delivery date exists). |
| A2 | Every delivered order was an online purchase, so the 7-day regret right (item 4.1) applies. |
| A3 | "Today" is `EMPORIO_TODAY` when set, otherwise the system clock; data ends in March 2026. |
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

## Open questions

None.

## Traceability

| Spec | Implemented in | Covers |
|---|---|---|
| 01 | `config.py`, `results.py`, `data.py` | data loading, cleaning, quality report |
| 02 | `pricing.py` | promotion, PIX, installments |
| 03 | `catalog.py` | search, product detail, availability |
| 04 | `policies.py` | policy sections |
| 05 | `db.py` | history and handoff storage |
| 06 | `session.py`, `orders.py` | verification, order status |
| 07 | `hours.py`, `returns.py`, `handoff.py` | return eligibility, handoff |
| 08 | `tools.py`, `prompt.py`, `agent.py`, `llm.py` | agent behavior |
| 09 | `cli.py` | chat, resume, export, replay |
| 10 | `evals/` | routing eval |
| 11 | `samples/`, `README.md` | deliverables |
