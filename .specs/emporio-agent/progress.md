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
| 05-persistence | 🔴 Not started | |
| 06-customer-orders | 🔴 Not started | |
| 07-returns-handoff | 🔴 Not started | |
| 08-agent-loop | 🔴 Not started | |
| 09-cli | 🔴 Not started | |
| 10-routing-eval | 🔴 Not started | |
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

---

## Decisions made during implementation

| Decision | Spec | Rationale |
|---|---|---|
