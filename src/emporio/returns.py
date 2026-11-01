"""Return, exchange and warranty eligibility (manual items 4.1 to 4.4, 8.1 and 8.2).

The data has no receipt date, so the estimated delivery stands in for it (assumption A1) and every
delivered order is treated as an online purchase (A2).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from emporio.data import StoreData
from emporio.orders import require_owned_order
from emporio.results import error
from emporio.session import SessionState

REGRET_DAYS = 7
PREFERENCE_DAYS = 7
DEFECT_EXCHANGE_DAYS = 30
LEGAL_WARRANTY_DAYS = 90
REASONS = ("regret", "defect", "preference")

_FINAL_SALE_QUESTION = (
    "Was the instrument bought with a custom setup or adjustments made to order, or as a "
    "'final sale' liquidation item? Those are not eligible (item 4.4)."
)
_NOT_DELIVERED_CODES = {
    "cancelled": "order_cancelled",
    "shipped": "not_received_yet",
    "pending": "not_shipped_yet",
    "confirmed": "not_shipped_yet",
}
_NOT_DELIVERED_NEXT_STEP = {
    "order_cancelled": "Tell the customer the order was cancelled; offer a handoff only if they want help.",
    "not_received_yet": "The order has not been received yet, so returns do not apply; tell the "
    "customer to contact the store if the delivery is late.",
    "not_shipped_yet": "The order has not shipped yet; the manual has no cancellation rule, so "
    "offer a handoff (category other) if the customer wants to cancel it.",
}


def _verdict(order: Any, reason: str, today: date, **fields: Any) -> dict[str, Any]:
    received_on = fields.pop("received_on", None)
    days_since_receipt = (
        (today - received_on).days if received_on and today >= received_on else None
    )
    result = {
        "order_id": int(order.order_id),
        "reason": reason,
        "eligible": False,
        "reason_code": "ok",
        "route": None,
        "received_on": received_on.isoformat() if received_on else None,
        "days_since_receipt": days_since_receipt,
        "days_since_purchase": (today - order.order_date).days,
        "deadline": None,
        "conditions": [],
        "ask_customer": [],
        "policy_sections": [],
        "next_step": None,
    }
    deadline = fields.pop("deadline", None)
    result["deadline"] = deadline.isoformat() if deadline else None
    result.update(fields)
    return result


def _windowed(order: Any, reason: str, today: date, received_on: date) -> dict[str, Any]:
    """Regret and preference share a 7-day window counted from receipt."""
    days = (today - received_on).days
    deadline = received_on + timedelta(days=REGRET_DAYS)
    if reason == "regret":
        sections = ["4.1", "4.4"]
        route = "return_refund"
        conditions = [
            "Original packaging, no signs of use, with all accessories and manuals (item 4.1).",
            (
                "Refund to the original payment method within 10 business days; the store pays "
                "the return shipping (item 4.1)."
            ),
        ]
        next_step = "open_handoff with category return_request"
    else:
        sections = ["4.3", "4.4"]
        route = "exchange"
        conditions = [
            "The product the customer wants must be in stock (check with search_products).",
            (
                "Perfect condition and original packaging; any price difference is charged or "
                "refunded (item 4.3)."
            ),
        ]
        next_step = "open_handoff with category return_request"

    if days <= REGRET_DAYS:
        return _verdict(
            order,
            reason,
            today,
            eligible=True,
            route=route,
            received_on=received_on,
            deadline=deadline,
            conditions=conditions,
            ask_customer=[_FINAL_SALE_QUESTION],
            policy_sections=sections,
            next_step=next_step,
        )
    return _verdict(
        order,
        reason,
        today,
        reason_code="window_expired",
        received_on=received_on,
        deadline=deadline,
        policy_sections=sections[:1],
        next_step=f"Explain that the 7-day window ended on {deadline.isoformat()}. If the product "
        "has a manufacturing defect, check again with reason 'defect'.",
    )


def _defect(order: Any, today: date, received_on: date) -> dict[str, Any]:
    reason = "defect"
    days_since_purchase = (today - order.order_date).days
    days_since_receipt = (today - received_on).days
    misuse = "Only manufacturing defects are covered; misuse, drops, humidity and unauthorized changes are not (item 4.2)."
    if days_since_purchase <= DEFECT_EXCHANGE_DAYS:
        return _verdict(
            order,
            reason,
            today,
            eligible=True,
            route="exchange",
            received_on=received_on,
            deadline=order.order_date + timedelta(days=DEFECT_EXCHANGE_DAYS),
            conditions=[misuse],
            ask_customer=["Describe the defect and when it appeared."],
            policy_sections=["4.2"],
            next_step="open_handoff with category defect",
        )
    if days_since_receipt <= LEGAL_WARRANTY_DAYS:
        return _verdict(
            order,
            reason,
            today,
            eligible=True,
            route="legal_warranty",
            received_on=received_on,
            deadline=received_on + timedelta(days=LEGAL_WARRANTY_DAYS),
            conditions=[
                misuse,
                (
                    "More than 30 days after the purchase the claim goes through the warranty: the "
                    "legal warranty lasts 90 days from receipt (item 8.1) and the store can mediate "
                    "with the manufacturer on request (item 4.2)."
                ),
            ],
            ask_customer=["Describe the defect and when it appeared."],
            policy_sections=["4.2", "8.1"],
            next_step="open_handoff with category defect",
        )
    return _verdict(
        order,
        reason,
        today,
        reason_code="window_expired",
        route="manufacturer_warranty",
        received_on=received_on,
        conditions=[
            (
                "The manufacturer's own warranty (6 months to 2 years, see the warranty certificate "
                "that came with the product) may still apply (item 8.2); the store can mediate on request."
            )
        ],
        policy_sections=["8.2"],
        next_step="Explain the manufacturer warranty and offer open_handoff (category other) "
        "if the customer wants the store to mediate.",
    )


def check_return_eligibility(
    data: StoreData,
    state: SessionState,
    order_id: int,
    reason: Literal["regret", "defect", "preference"],
    today: date,
) -> dict[str, Any]:
    if reason not in REASONS:
        return error("invalid_argument", f"reason must be one of {', '.join(REASONS)}.")
    order, failure = require_owned_order(data, state, order_id)
    if failure is not None:
        return failure

    if order.status != "delivered":
        code = _NOT_DELIVERED_CODES[order.status]
        return _verdict(
            order, reason, today, reason_code=code, next_step=_NOT_DELIVERED_NEXT_STEP[code]
        )

    received_on = order.estimated_delivery
    if today < received_on:
        return _verdict(
            order,
            reason,
            today,
            reason_code="not_received_yet",
            received_on=received_on,
            next_step=_NOT_DELIVERED_NEXT_STEP["not_received_yet"],
        )
    if reason == "defect":
        return _defect(order, today, received_on)
    return _windowed(order, reason, today, received_on)
