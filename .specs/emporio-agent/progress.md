# Empório da Música agent: implementation progress

> Updated in the same commit that finishes each spec.

**Last update:** 2026-10-31

---

## Overall status

| Spec | Status | Notes |
|---|---|---|
| 01-foundation-data | 🟢 Done | 21 tests, ruff clean |
| 02-pricing | 🟢 Done | 30 tests |
| 03-catalog | 🔴 Not started | |
| 04-policy-retrieval | 🔴 Not started | |
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

---

## Decisions made during implementation

| Decision | Spec | Rationale |
|---|---|---|
