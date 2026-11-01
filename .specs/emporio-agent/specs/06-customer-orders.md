# Spec 06: Customer verification and orders

**Status:** 🟡 Draft
**Author:** renatoctti
**Date:** 2026-10-31
**Scope:** session verification state and order tools
**Depends on:** 01
**Delivery:** autonomous (after 01)

---

## Summary

Three tool functions: `verify_customer` (proves the customer owns an order), `get_order_status`
and `list_my_orders`. Verification is stored in a `SessionState` object kept by the code, not by
the model, so a prompt cannot talk the agent into skipping it.

## Context

Order data is personal data (the manual cites LGPD, item 9). Order numbers are sequential and
guessable, and a customer's name is not a secret, so ownership is proven with the e-mail or phone
registered on that order. Customers 11 and 43 share an e-mail, so identity is checked against the
customer who **owns the order**, never by searching customers by e-mail (assumption A12).

---

## Allowed files

**Production**

- `src/emporio/session.py` (new): `SessionState`, `MAX_FAILED_VERIFICATIONS`
- `src/emporio/orders.py` (new)

**Tests**

- `tests/test_orders.py` (new)

**Do not touch:** every other file.

---

## Functional requirements

| ID | Requirement | Priority | Acceptance criterion |
|---|---|---|---|
| 🟡 RF-01 | `verify_customer(order_id, contact)` succeeds when `contact` is the e-mail (case and surrounding spaces ignored) or the phone (digits only, leading `55` ignored, DDD required) of the customer who owns the order; on success it stores that customer id in the state and returns the first name | Must | Order 8 with `anacarol.ferreira@coldmail.com` and with `(67) 99654-7821` and `+55 67 99654 7821` all verify customer 2 |
| 🟡 RF-02 | Any failure (wrong contact, unknown order) returns the **same** answer `{"verified": False, "attempts_left": n}` and increments `failed_verifications`, so order existence is not revealed | Must | Wrong e-mail on order 8 and any e-mail on order 9999 return identical payloads (except `attempts_left`) |
| 🟡 RF-03 | After `MAX_FAILED_VERIFICATIONS` (3) failures the state is locked: further calls return `verification_locked` without checking anything | Must | Fourth call with the right e-mail still returns `verification_locked` |
| 🟡 RF-04 | `get_order_status(order_id)` requires a verified state and an order owned by the verified customer; otherwise `not_verified` or `order_not_found` (the same code for "does not exist" and "belongs to someone else") | Must | Verified as customer 2, order 10 returns `order_not_found` |
| 🟡 RF-05 | `get_order_status` returns status, a status meaning (A6), date, recorded `total_brl` (A5), payment `{method, installments}`, items (`product_id`, `name`, `quantity`), tracking code, estimated delivery, notes and `estimated_delivery_passed` | Must | Order 3 returns total 3450.0 (not 3498) with 2 items of product 130; order 8 has tracking `BRJL5544332BR` |
| 🟡 RF-06 | `estimated_delivery_passed` is `True` when the status is `shipped` and `today` is after the estimated date, `False` when it is not, `None` when there is no estimated date or the order is not shipped | Must | Order 8 with today 2026-03-25 gives `True`; with today 2026-02-20 gives `False`; order 1 gives `None` |
| 🟡 RF-07 | `list_my_orders()` requires a verified state and returns that customer's orders newest first with `order_id`, `order_date`, `status`, `total_brl`, `item_count` | Must | Customer 3 (orders 1 and 19) gets order 19 first |
| 🟡 RF-08 | Verification does not carry across sessions: a new `SessionState` starts unverified | Must | Fresh state has `verified_customer_id is None` |

---

## Expected behavior

- A second successful verification for a different order of a different customer replaces the verified customer (the state holds one identity at a time).
- Cancelled orders include the `notes` text (the reason).
- Tracking code and estimated delivery are `None` for orders not yet shipped; the agent must not invent them.

---

## Contracts

**`src/emporio/session.py`** 🟡

```python
MAX_FAILED_VERIFICATIONS: int = 3


@dataclass
class SessionState:
    verified_customer_id: int | None = None
    failed_verifications: int = 0
```

**`src/emporio/orders.py`** 🟡

```python
STATUS_MEANING: dict[str, str]    # assumption A6, English sentences for the model

def verify_customer(data: StoreData, state: SessionState, order_id: int, contact: str) -> dict[str, Any]
# {"verified": True, "customer_first_name": "Ana"}
# {"verified": False, "attempts_left": 2}
# {"error": {"code": "verification_locked", ...}}

def get_order_status(data: StoreData, state: SessionState, order_id: int, today: date) -> dict[str, Any]
# {"order_id", "status", "status_meaning", "order_date", "total_brl",
#  "payment": {"method": "credit", "installments": 6}, "items": [{"product_id", "name", "quantity"}],
#  "tracking_code": str | None, "estimated_delivery": str | None, "estimated_delivery_passed": bool | None,
#  "notes": str | None}
# or {"error": {"code": "not_verified" | "order_not_found", ...}}

def list_my_orders(data: StoreData, state: SessionState) -> dict[str, Any]
# {"orders": [{"order_id", "order_date", "status", "total_brl", "item_count"}...]}
# or {"error": {"code": "not_verified", ...}}
```

---

## Edge cases

| ID | Scenario | Trigger | Expected behavior |
|---|---|---|---|
| 🟡 EC-01 | Shared e-mail | `bruno.martins@jmail.com` on order 10 (customer 11) | Verifies customer 11, never customer 43; `list_my_orders` returns order 10 only |
| 🟡 EC-02 | Phone without DDD | `99654-7821` | Not verified (counts as a failure) |
| 🟡 EC-03 | Contact is empty or blank | `""` | `invalid_argument`, not counted as a failure |
| 🟡 EC-04 | Cancelled order | order 17 | Status `cancelled`, notes "Pedido cancelado pelo cliente antes do processamento" |
| 🟡 EC-05 | Order id not an integer | `"abc"` | `invalid_argument` |

---

## Minimum test cases

| # | Target | Scenario | Fixture | Expected result | Test file |
|---|---|---|---|---|---|
| 🟡 T-01 | `verify_customer` | e-mail and phone formats | order 8 | RF-01 | `tests/test_orders.py` |
| 🟡 T-02 | `verify_customer` | indistinguishable failures and lock | orders 8, 9999 | RF-02, RF-03 | `tests/test_orders.py` |
| 🟡 T-03 | `verify_customer` | shared e-mail, bad inputs | orders 10, phone without DDD, blank | EC-01 to EC-03, EC-05 | `tests/test_orders.py` |
| 🟡 T-04 | `get_order_status` | requires verification and ownership | fresh state, then customer 2 | `not_verified`, `order_not_found` | `tests/test_orders.py` |
| 🟡 T-05 | `get_order_status` | content for orders 3, 8, 17 | verified states | RF-05, EC-04 | `tests/test_orders.py` |
| 🟡 T-06 | `get_order_status` | delivery passed flag | order 8 with two dates, order 1 | RF-06 | `tests/test_orders.py` |
| 🟡 T-07 | `list_my_orders` | ordering and unverified | customer 3 | RF-07, `not_verified` | `tests/test_orders.py` |

### Acceptance criterion

```bash
python -m pytest tests/test_orders.py -q
```

---

## Implementation checklist

- [ ] 🟡 `git diff --stat` checked against **Allowed files**
- [ ] 🟡 Tests written before the code
- [ ] 🟡 Fixtures come from the real `data/`; field names identical to the contract
- [ ] 🟡 Compare contacts with `hmac.compare_digest` or equality on normalized strings; never log the contact
- [ ] 🟡 Business errors returned with `results.error`
- [ ] 🟡 `ruff check` and `ruff format --check` pass

## Open questions

None.

## Architectural adherence

| Rule | Status | Note |
|---|---|---|
| Verification state lives in code, not in the prompt | 🟡 | |
| Domain modules do not import the LLM client | 🟡 | |
| No silent catch | 🟡 | |
| Scope respected | 🟡 | |