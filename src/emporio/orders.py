"""Customer verification and order tools.

Order data is personal data (manual item 9, LGPD). Ownership is proven with the e-mail or phone
registered on the order, and the check is made against the customer who *owns* that order: two
customers share an e-mail address, so searching customers by e-mail would be ambiguous.
"""

from __future__ import annotations

import hmac
import re
from datetime import date
from typing import Any

from emporio.data import StoreData
from emporio.results import error
from emporio.session import MAX_FAILED_VERIFICATIONS, SessionState

# Assumption A6: the data has no status glossary, these are the meanings the agent may state.
STATUS_MEANING: dict[str, str] = {
    "pending": "Order registered; waiting for the payment to be confirmed.",
    "confirmed": "Payment confirmed; the order is being prepared and has not shipped yet.",
    "shipped": "The order was shipped and is on its way; the tracking code follows the delivery.",
    "delivered": "The order was delivered.",
    "cancelled": "The order was cancelled; the reason is in the notes.",
}

_NOT_VERIFIED = (
    "Ask the customer for the order number and the e-mail or phone registered on it, "
    "then call verify_customer."
)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _phone_digits(text: str) -> str:
    digits = re.sub(r"\D", "", text)
    return digits[2:] if digits.startswith("55") and len(digits) > 11 else digits


def _contact_matches(customer: Any, contact: str) -> bool:
    contact = contact.strip()
    if "@" in contact:
        candidate, expected = contact.lower(), customer.email_norm
    else:
        candidate, expected = _phone_digits(contact), customer.phone_digits
    return hmac.compare_digest(candidate.encode(), expected.encode())


def verify_customer(
    data: StoreData, state: SessionState, order_id: int, contact: str
) -> dict[str, Any]:
    if not _is_int(order_id):
        return error("invalid_argument", "order_id must be an integer.")
    if not isinstance(contact, str) or not contact.strip():
        return error("invalid_argument", "contact must be the customer's e-mail or phone.")
    if state.failed_verifications >= MAX_FAILED_VERIFICATIONS:
        return error(
            "verification_locked",
            "Too many failed attempts. Do not try again; offer a human attendant (open_handoff).",
        )

    order = data.orders[data.orders.order_id == order_id]
    owner = None
    if not order.empty:
        owners = data.customers[data.customers.customer_id == order.iloc[0].customer_id]
        owner = next(owners.itertuples())
    if owner is not None and _contact_matches(owner, contact):
        state.verified_customer_id = int(owner.customer_id)
        state.failed_verifications = 0
        return {"verified": True, "customer_first_name": owner.name.split()[0]}

    # Same answer for a wrong contact and for an unknown order: existence is not revealed.
    state.failed_verifications += 1
    return {
        "verified": False,
        "attempts_left": MAX_FAILED_VERIFICATIONS - state.failed_verifications,
    }


def require_owned_order(
    data: StoreData, state: SessionState, order_id: int
) -> tuple[Any | None, dict[str, Any] | None]:
    """The order row when it belongs to the verified customer, else `(None, error result)`."""
    if not _is_int(order_id):
        return None, error("invalid_argument", "order_id must be an integer.")
    if state.verified_customer_id is None:
        return None, error("not_verified", _NOT_VERIFIED)
    rows = data.orders[
        (data.orders.order_id == order_id) & (data.orders.customer_id == state.verified_customer_id)
    ]
    if rows.empty:
        # Same answer for "does not exist" and "belongs to someone else".
        return None, error("order_not_found", "No order with that number for this customer.")
    return next(rows.itertuples()), None


def get_order_status(
    data: StoreData, state: SessionState, order_id: int, today: date
) -> dict[str, Any]:
    order, failure = require_owned_order(data, state, order_id)
    if failure is not None:
        return failure

    names = dict(zip(data.products.product_id, data.products.name, strict=True))
    lines = data.order_items[data.order_items.order_id == order_id]
    eta = order.estimated_delivery
    passed = (today > eta) if order.status == "shipped" and eta is not None else None
    return {
        "order_id": int(order.order_id),
        "status": order.status,
        "status_meaning": STATUS_MEANING[order.status],
        "order_date": order.order_date.isoformat(),
        "total_brl": float(order.total_brl),
        "payment": {
            "method": order.payment_kind,
            "installments": None if order.installments is None else int(order.installments),
        },
        "items": [
            {
                "product_id": int(line.product_id),
                "name": names[line.product_id],
                "quantity": int(line.quantity),
            }
            for line in lines.itertuples()
        ],
        "tracking_code": order.tracking_code,
        "estimated_delivery": eta.isoformat() if eta is not None else None,
        "estimated_delivery_passed": passed,
        "notes": order.notes,
    }


def list_my_orders(data: StoreData, state: SessionState) -> dict[str, Any]:
    if state.verified_customer_id is None:
        return error("not_verified", _NOT_VERIFIED)
    mine = data.orders[data.orders.customer_id == state.verified_customer_id]
    mine = mine.sort_values(["order_date", "order_id"], ascending=False)
    units = data.order_items.groupby("order_id").quantity.sum()
    return {
        "orders": [
            {
                "order_id": int(o.order_id),
                "order_date": o.order_date.isoformat(),
                "status": o.status,
                "total_brl": float(o.total_brl),
                "item_count": int(units.get(o.order_id, 0)),
            }
            for o in mine.itertuples()
        ]
    }
