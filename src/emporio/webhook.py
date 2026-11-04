"""Optional webhook: tells the store team's own tool when a new ticket is opened (spec 24)."""

from __future__ import annotations

import json
import logging
import urllib.request
from collections.abc import Callable
from typing import Any

from emporio.db import Handoff

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 3.0
_CATEGORY_LABELS = {
    "complaint": "Reclamação",
    "return_request": "Devolução",
    "defect": "Defeito",
    "other": "Outro",
}

Notifier = Callable[[Handoff], None]


def handoff_body(ticket: Handoff) -> dict[str, Any]:
    """The message for the receiver. The customer's name, contact and id are never added."""
    label = _CATEGORY_LABELS.get(ticket.category, ticket.category)
    due = ticket.due_at.strftime("%d/%m às %H:%M")
    order = f" · pedido {ticket.order_id}" if ticket.order_id is not None else ""
    return {
        "event": "handoff.created",
        # `text` is what a Slack incoming webhook shows; the other fields are for n8n and the like
        "text": f"Novo chamado {ticket.protocol} ({label}){order}. Responder até {due}.",
        "protocol": ticket.protocol,
        "category": ticket.category,
        "summary": ticket.summary,
        "order_id": ticket.order_id,
        "session_id": ticket.session_id,
        "created_at": ticket.created_at.isoformat(timespec="seconds"),
        "due_at": ticket.due_at.isoformat(timespec="seconds"),
    }


def make_notifier(
    url: str | None,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    timeout: float = TIMEOUT_SECONDS,
) -> Notifier | None:
    """A function that posts a new ticket to `url`, or None when no address is set.

    shortcut: synchronous call with a short timeout and no retry, a failed message is lost
    (the ticket stays in the database); upgrade to a queue when the team depends on it.
    """
    if url is None:
        return None

    def notify(ticket: Handoff) -> None:
        try:
            request = urllib.request.Request(
                url,
                data=json.dumps(handoff_body(ticket), ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with opener(request, timeout=timeout):
                pass
        except Exception as exc:  # noqa: BLE001  (the ticket is stored; the answer must not fail)
            log.warning("handoff webhook failed: %s", exc)

    return notify
