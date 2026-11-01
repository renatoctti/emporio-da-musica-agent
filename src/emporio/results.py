"""Helpers shared by every tool: error results and money rounding."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def error(code: str, message: str) -> dict[str, dict[str, str]]:
    """Business error returned to the model (never raised)."""
    return {"error": {"code": code, "message": message}}


def is_error(result: Mapping[str, Any]) -> bool:
    return "error" in result


def round_brl(value: float) -> float:
    """Round half-up to cents; goes through `str` so 2.675 is treated as 2.675, not 2.67499..."""
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
