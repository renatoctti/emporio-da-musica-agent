"""Per-conversation state kept by the code (never by the model)."""

from __future__ import annotations

from dataclasses import dataclass

MAX_FAILED_VERIFICATIONS: int = 3


@dataclass
class SessionState:
    verified_customer_id: int | None = None
    failed_verifications: int = 0
