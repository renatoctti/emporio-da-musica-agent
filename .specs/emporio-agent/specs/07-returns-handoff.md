# Spec 07: Business hours, return eligibility and handoff

**Status:** 🟢 Implemented
**Author:** renatoctti
**Date:** 2026-10-31
**Scope:** store hours arithmetic, return/exchange rules, handoff ticket creation
**Depends on:** 01, 05, 06
**Delivery:** autonomous (after its dependencies)

---

## Summary

Deterministic return rules (items 4.1 to 4.4, 8.1, 8.2) and the handoff flow (item 7.3, complaints:
"register and forward, return within 24 business hours"). The model asks these tools instead of
interpreting day counts itself.

## Context

A customer saying "me arrependi" needs a verdict by dates: 7 days from receipt for regret, 30 days
from purchase for defects, 90 days legal warranty from receipt. Data has no receipt date, so the
estimated delivery stands in for it (A1), and delivered orders are treated as online (A2).

---

## Allowed files

**Production**

- `src/emporio/hours.py` (new)
- `src/emporio/returns.py` (new)
- `src/emporio/handoff.py` (new)

**Tests**

- `tests/test_hours.py` (new)
- `tests/test_returns.py` (new)
- `tests/test_handoff.py` (new)

**Do not touch:** every other file.

---

## Functional requirements

| ID | Requirement | Priority | Acceptance criterion |
|---|---|---|---|
| ✅ RF-01 | `STORE_HOURS` encodes item 2: Mon-Fri 09:00-18:00, Sat 09:00-13:00, Sun closed; `is_open(now)` and `next_opening(now)` follow it | Must | Sat 12:59 open, Sat 13:00 closed, Sun 10:00 closed, next opening Mon 09:00 |
| ✅ RF-02 | `add_business_hours(start, hours)` adds open hours only; a start outside opening hours begins at the next opening | Must | Mon 10:00 + 24h = Wed 16:00; Fri 17:00 + 2h = Sat 10:00; Sat 12:00 + 24h = Wed 14:00 (1h Sat, 9h Mon, 9h Tue, 5h Wed) |
| ✅ RF-03 | `check_return_eligibility(order_id, reason, today)` requires verification and ownership (`not_verified`, `order_not_found`) and a `reason` of `regret`, `defect` or `preference` (else `invalid_argument`) | Must | Reason `"other"` returns `invalid_argument` |
| ✅ RF-04 | Orders that are not `delivered` return `eligible: False` with `reason_code`: `order_cancelled`, `not_received_yet` (shipped, or `today` before the estimated delivery), `not_shipped_yet` (pending, confirmed) | Must | Order 17 gives `order_cancelled`; order 8 gives `not_received_yet`; order 12 gives `not_shipped_yet` |
| ✅ RF-05 | `regret`: eligible while days since receipt is at most 7, route `return_refund`, deadline receipt + 7, policy sections `4.1`, `4.4`; afterwards `eligible: False`, `reason_code: "window_expired"` | Must | Order 7 (received 2026-02-17): today 2026-02-19 eligible, 2026-02-24 eligible (day 7), 2026-02-25 not |
| ✅ RF-06 | `preference`: eligible while days since receipt is at most 7, route `exchange`, policy `4.3`, condition "depends on the desired product being in stock" | Must | Same windows as RF-05 |
| ✅ RF-07 | `defect`: eligible with route `exchange` while days since **purchase** is at most 30 (policy `4.2`); then route `legal_warranty` while days since receipt is at most 90 (policy `4.2`, `8.1`); after that `eligible: False`, route `manufacturer_warranty` (policy `8.2`) | Must | Order 7 (purchase 2026-02-03): today 2026-03-05 exchange; 2026-03-25 legal warranty; 2026-06-01 manufacturer warranty |
| ✅ RF-08 | Every eligible verdict carries `conditions` (original packaging, no signs of use, accessories and manuals for regret; no misuse for defects) and `ask_customer` (whether the item had custom setup or was bought as "final sale", item 4.4) | Must | Lists non-empty for eligible verdicts |
| ✅ RF-09 | `open_handoff(category, summary, order_id, session_id, now)` validates the category against `HANDOFF_CATEGORIES`, a non-empty summary of at most 600 characters, and, when `order_id` is given, verification and ownership | Must | Empty summary returns `invalid_argument`; order of another customer returns `order_not_found` |
| ✅ RF-10 | A handoff without `order_id` is allowed for an unverified customer (complaints); the stored `customer_id` is the verified customer or `None` | Must | Ticket stored with `customer_id None` |
| ✅ RF-11 | The deadline `due_at` is `add_business_hours(now, 24)`; the result returns `protocol`, `category`, `status "open"`, `due_at` (ISO), `store_open_now` and `duplicate` | Must | Created Mon 2026-03-23 10:00 returns due Wed 2026-03-25 16:00 |
| ✅ RF-12 | If an open ticket already exists for the same order and category it is returned with `duplicate: True` and no new row | Should | Second identical call keeps one row |

---

## Expected behavior

- Dates in outputs are ISO strings. `days_since_receipt` and `days_since_purchase` are integers.
- Receipt date = `estimated_delivery` (A1). If `today` is before it the order is `not_received_yet`.
- `next_step` in an eligible verdict names the follow-up: "open_handoff with category return_request" (regret, preference) or "defect" (defects).
- Holidays are ignored (A7).

---

## Contracts

**`src/emporio/hours.py`** ✅

```python
STORE_HOURS: dict[int, tuple[time, time] | None]   # weekday() -> (open, close) or None
def is_open(now: datetime) -> bool
def next_opening(now: datetime) -> datetime         # now itself when open
def add_business_hours(start: datetime, hours: float) -> datetime
```

**`src/emporio/returns.py`** ✅

```python
REGRET_DAYS = 7; PREFERENCE_DAYS = 7; DEFECT_EXCHANGE_DAYS = 30; LEGAL_WARRANTY_DAYS = 90

def check_return_eligibility(
    data: StoreData, state: SessionState, order_id: int,
    reason: Literal["regret", "defect", "preference"], today: date,
) -> dict[str, Any]
# {"order_id", "reason", "eligible": bool, "reason_code": "ok" | "window_expired" | "order_cancelled"
#  | "not_received_yet" | "not_shipped_yet", "route": "return_refund" | "exchange" | "legal_warranty"
#  | "manufacturer_warranty" | None, "received_on": str | None, "days_since_receipt": int | None,
#  "days_since_purchase": int, "deadline": str | None, "conditions": [str], "ask_customer": [str],
#  "policy_sections": [str], "next_step": str | None}
```

**`src/emporio/handoff.py`** ✅

```python
MAX_SUMMARY_CHARS = 600
RESPONSE_BUSINESS_HOURS = 24

def open_handoff(
    data: StoreData, state: SessionState, store: HandoffStore, *,
    category: str, summary: str, order_id: int | None, session_id: str | None, now: datetime,
) -> dict[str, Any]
# {"protocol": "EMP-20260325-0001", "category", "status": "open", "due_at": "2026-03-27T16:00:00",
#  "store_open_now": bool, "duplicate": bool}
```

---

## Edge cases

| ID | Scenario | Trigger | Expected behavior |
|---|---|---|---|
| ✅ EC-01 | Request on the last day | days since receipt exactly 7 | Eligible |
| ✅ EC-02 | Out-of-hours handoff | created Sunday 15:00 | Deadline counts from Monday 09:00; `store_open_now False` |
| ✅ EC-03 | Verified customer without order | `order_id None` | Ticket linked to the customer only |
| ✅ EC-04 | Summary with 601 characters | `"a" * 601` | `invalid_argument` |

---

## Minimum test cases

| # | Target | Scenario | Fixture | Expected result | Test file |
|---|---|---|---|---|---|
| ✅ T-01 | `is_open`, `next_opening` | boundaries | datetimes of RF-01 | as listed | `tests/test_hours.py` |
| ✅ T-02 | `add_business_hours` | day crossings, Saturday, Sunday, out-of-hours start | table of cases | exact datetimes | `tests/test_hours.py` |
| ✅ T-03 | `check_return_eligibility` | non-delivered orders | orders 17, 8, 12 | RF-04 | `tests/test_returns.py` |
| ✅ T-04 | `check_return_eligibility` | regret and preference windows | order 7, three dates | RF-05, RF-06, EC-01 | `tests/test_returns.py` |
| ✅ T-05 | `check_return_eligibility` | defect routes | order 7, three dates | RF-07 | `tests/test_returns.py` |
| ✅ T-06 | `check_return_eligibility` | verification, ownership, bad reason, conditions | fresh state, other customer | RF-03, RF-08 | `tests/test_returns.py` |
| ✅ T-07 | `open_handoff` | creation, deadline, protocol | in-memory store, verified customer 14 | RF-09, RF-11 | `tests/test_handoff.py` |
| ✅ T-08 | `open_handoff` | validation, unverified complaint, duplicate | RF-09, RF-10, RF-12, EC-02 to EC-04 | as listed | `tests/test_handoff.py` |

### Acceptance criterion

```bash
python -m pytest tests/test_hours.py tests/test_returns.py tests/test_handoff.py -q
```

---

## Implementation checklist

- [x] ✅ `git diff --stat` checked against **Allowed files**
- [x] ✅ Tests written before the code
- [x] ✅ Window lengths are named constants; policy section ids returned come from the manual numbering
- [x] ✅ Business errors returned with `results.error`; reuse `orders` ownership helper if spec 06 exposes one, otherwise duplicate nothing: import from `orders`
- [x] ✅ `ruff check` and `ruff format --check` pass

## Open questions

None.

## Architectural adherence

| Rule | Status | Note |
|---|---|---|
| Domain modules do not import the LLM client | ✅ | |
| No silent catch | ✅ | |
| Scope respected | ✅ | |