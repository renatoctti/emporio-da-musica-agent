# Spec 02: Price quote

**Status:** 🟡 Draft
**Author:** renatoctti
**Date:** 2026-10-31
**Scope:** pure pricing rules (promotion, PIX, installments)
**Depends on:** none
**Delivery:** autonomous

---

## Summary

A pure function that turns a list price (and optionally an active promotion) into the full price
picture a customer needs: promotional price, PIX price, installment options and whether payments
can be combined. Implements manual items 3, 3.1 and 6.2 so the model never does the arithmetic.

## Context

Customers ask "how much is it, can I split it in 10x, is there a PIX discount?". Wrong numbers are
"propaganda enganosa" (manual item 7.1). Isolating the rules makes them unit-testable without data.

---

## Allowed files

**Production**

- `src/emporio/pricing.py` (new)

**Tests**

- `tests/test_pricing.py` (new)

**Do not touch:** every other file.

---

## Functional requirements

| ID | Requirement | Priority | Acceptance criterion |
|---|---|---|---|
| 🟡 RF-01 | `build_price_quote` returns the list price and, when a promotion percent is given, a `promotion` block with the original price, the percent and the promotional price | Must | 549.00 with 20% gives `price_brl == 439.2` and `promotion.discount_percent == 20` |
| 🟡 RF-02 | The PIX discount is 5% over the list price and **only applies when there is no promotion** (item 6.2: promotions do not stack) | Must | 11499 without promotion gives `pix_price_brl == 10924.05`; 5999 with an 8% promotion gives `pix_price_brl is None` and a note saying the discounts do not stack |
| 🟡 RF-03 | Installments use the card price (`price_brl`, never the PIX price). The minimum installment is: 1x none; 2x to 3x R$ 50.00; 4x to 6x R$ 80.00; 7x to 12x R$ 100.00 (item 3.1, assumption A8). An option is allowed when the rounded installment is at least the minimum | Must | 439.20: options are 1x to 5x; 6x (73.20) is not allowed; `installments.max == 5` |
| 🟡 RF-04 | `installments.options` lists every allowed `n` with its `installment_brl`; `n == 1` is always allowed | Must | Price 40.00 gives only 1x |
| 🟡 RF-05 | `combined_payment_allowed` is true when the card price is above R$ 2,000.00 (item 3.1) | Should | 2000.00 gives false; 2000.01 gives true |
| 🟡 RF-06 | `min_installment_brl(n)` returns the minimum for `1 <= n <= 12` and raises `ValueError` otherwise | Must | `min_installment_brl(7) == 100.0`; `13` raises |
| 🟡 RF-07 | A non-positive price, or a promotion percent outside 0 < p < 100, raises `ValueError` | Must | `build_price_quote(0)` raises |

---

## Expected behavior

1. Promotional price = `round_brl(list * (1 - p / 100))`.
2. Card price = promotional price when a promotion exists, else list price.
3. PIX price = `round_brl(list * 0.95)` only when there is no promotion.
4. For `n` in 1..12 compute `round_brl(card / n)` and keep the allowed ones.

---

## Contracts

**`src/emporio/pricing.py`** 🟡

```python
PIX_DISCOUNT_PERCENT: float = 5.0
COMBINED_PAYMENT_THRESHOLD_BRL: float = 2000.0
MAX_INSTALLMENTS: int = 12

def min_installment_brl(n: int) -> float

def build_price_quote(
    list_price_brl: float,
    promotion_percent: float | None = None,
    promotion_description: str | None = None,
) -> dict[str, Any]
# {
#   "list_price_brl": 549.0,
#   "promotion": None | {"description": str | None, "discount_percent": 20.0, "price_brl": 439.2},
#   "price_brl": 439.2,                      # card / debit / boleto price
#   "pix_price_brl": 521.55 | None,
#   "pix_note": str | None,                  # set when pix_price_brl is None because of a promotion
#   "installments": {"max": 5, "options": [{"n": 1, "installment_brl": 439.2}, ...]},
#   "combined_payment_allowed": False,
# }
```

Errors: `ValueError` for invalid inputs (programming errors, not customer conditions).

---

## Edge cases

| ID | Scenario | Trigger | Expected behavior |
|---|---|---|---|
| 🟡 EC-01 | Rounding at the half cent | list 0.0 not allowed; 2.675 style values | Half-up via decimal arithmetic |
| 🟡 EC-02 | Price below R$ 50 | 49.90 | Only 1x |
| 🟡 EC-03 | Exactly at a minimum | 150.00 (3x of 50.00) | 3x allowed; 4x not allowed (37.50 below 80) |
| 🟡 EC-04 | Large price | 19567.00 | max is 12 (1630.58) |

---

## Minimum test cases

| # | Target | Scenario | Fixture | Expected result | Test file |
|---|---|---|---|---|---|
| 🟡 T-01 | `build_price_quote` | promotion | `(549.0, 20, "Desconto Exclusivo")` | price 439.2, installments max 5, pix None with note | `tests/test_pricing.py` |
| 🟡 T-02 | `build_price_quote` | no promotion | `(11499.0)` | pix 10924.05, max 12 | `tests/test_pricing.py` |
| 🟡 T-03 | `build_price_quote` | EC-02, EC-03 | 49.9, 150.0 | as listed | `tests/test_pricing.py` |
| 🟡 T-04 | `min_installment_brl` | boundaries | 1, 3, 4, 6, 7, 12, 0, 13 | 0, 50, 80, 80, 100, 100, `ValueError` twice | `tests/test_pricing.py` |
| 🟡 T-05 | `build_price_quote` | invalid input | 0, -5, promo 100 | `ValueError` | `tests/test_pricing.py` |
| 🟡 T-06 | `build_price_quote` | combined payment threshold | 2000.0, 2000.01 | false, true | `tests/test_pricing.py` |

### Acceptance criterion

```bash
python -m pytest tests/test_pricing.py -q
```

---

## Implementation checklist

- [ ] 🟡 `git diff --stat` checked against **Allowed files**
- [ ] 🟡 Tests written before the code
- [ ] 🟡 Uses `results.round_brl` from spec 01 (do not re-implement rounding)
- [ ] 🟡 Constants named, no magic numbers inline
- [ ] 🟡 `ruff check` and `ruff format --check` pass

## Open questions

None.

## Architectural adherence

| Rule | Status | Note |
|---|---|---|
| Domain modules do not import the LLM client | 🟡 | |
| No silent catch | 🟡 | |
| Scope respected | 🟡 | |