"""Human handoff: registers a ticket for the store team (manual item 7.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from emporio.data import StoreData
from emporio.db import HANDOFF_CATEGORIES, Handoff, HandoffStore
from emporio.hours import add_business_hours, is_open
from emporio.orders import require_owned_order
from emporio.results import error
from emporio.session import SessionState

MAX_SUMMARY_CHARS = 600
RESPONSE_BUSINESS_HOURS = 24


def _payload(ticket: Handoff, now: datetime, *, duplicate: bool) -> dict[str, Any]:
    return {
        "protocol": ticket.protocol,
        "category": ticket.category,
        "status": ticket.status,
        "due_at": ticket.due_at.isoformat(timespec="seconds"),
        "store_open_now": is_open(now),
        "duplicate": duplicate,
    }


def open_handoff(
    data: StoreData,
    state: SessionState,
    store: HandoffStore,
    *,
    category: str,
    summary: str,
    order_id: int | None,
    session_id: str | None,
    now: datetime,
) -> dict[str, Any]:
    if category not in HANDOFF_CATEGORIES:
        return error(
            "invalid_argument", f"category must be one of {', '.join(HANDOFF_CATEGORIES)}."
        )
    if not isinstance(summary, str) or not summary.strip():
        return error("invalid_argument", "summary must describe the case in a few words.")
    summary = summary.strip()
    if len(summary) > MAX_SUMMARY_CHARS:
        return error(
            "invalid_argument", f"summary must have at most {MAX_SUMMARY_CHARS} characters."
        )

    if order_id is not None:
        _, failure = require_owned_order(data, state, order_id)
        if failure is not None:
            return failure
        existing = store.find_open(order_id, category)
        if existing is not None:
            return _payload(existing, now, duplicate=True)

    ticket = store.create(
        category=category,
        summary=summary,
        customer_id=state.verified_customer_id,
        order_id=order_id,
        session_id=session_id,
        created_at=now,
        due_at=add_business_hours(now, RESPONSE_BUSINESS_HOURS),
    )
    return _payload(ticket, now, duplicate=False)
