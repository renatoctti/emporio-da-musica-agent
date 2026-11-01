"""Price quote for one product: promotion, PIX discount and installment options.

Rules come from the store manual: item 3 (payment methods), item 3.1 (installments) and
item 6.2 (promotions do not stack with the PIX discount).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from emporio.results import round_brl

PIX_DISCOUNT_PERCENT: float = 5.0
COMBINED_PAYMENT_THRESHOLD_BRL: float = 2000.0
MAX_INSTALLMENTS: int = 12

# Minimum installment value per number of installments (item 3.1; "up to 3x, except below
# R$ 50" is read as a R$ 50 minimum for 2x and 3x, assumption A8).
_MIN_INSTALLMENT_TIERS: tuple[tuple[int, float], ...] = (
    (1, 0.0),
    (3, 50.0),
    (6, 80.0),
    (12, 100.0),
)

_PIX_NOTE = "The PIX discount does not stack with promotional prices (manual item 6.2)."


def min_installment_brl(n: int) -> float:
    if not 1 <= n <= MAX_INSTALLMENTS:
        raise ValueError(f"installments must be between 1 and {MAX_INSTALLMENTS}, got {n}")
    return next(minimum for limit, minimum in _MIN_INSTALLMENT_TIERS if n <= limit)


def _discounted(price: float, percent: float) -> float:
    """`price` minus `percent`%, computed exactly in decimal before the final rounding."""
    factor = (Decimal(100) - Decimal(str(percent))) / Decimal(100)
    return round_brl(float(Decimal(str(price)) * factor))


def _installment_options(card_price: float) -> list[dict[str, float | int]]:
    options = []
    for n in range(1, MAX_INSTALLMENTS + 1):
        installment = round_brl(float(Decimal(str(card_price)) / Decimal(n)))
        if installment >= min_installment_brl(n):
            options.append({"n": n, "installment_brl": installment})
    return options


def build_price_quote(
    list_price_brl: float,
    promotion_percent: float | None = None,
    promotion_description: str | None = None,
) -> dict[str, Any]:
    if list_price_brl <= 0:
        raise ValueError(f"price must be positive, got {list_price_brl}")
    if promotion_percent is not None and not 0 < promotion_percent < 100:
        raise ValueError(f"promotion percent must be between 0 and 100, got {promotion_percent}")

    promotion = None
    card_price = list_price_brl
    if promotion_percent is not None:
        card_price = _discounted(list_price_brl, promotion_percent)
        promotion = {
            "description": promotion_description,
            "discount_percent": float(promotion_percent),
            "price_brl": card_price,
        }

    pix_price = None if promotion else _discounted(list_price_brl, PIX_DISCOUNT_PERCENT)
    options = _installment_options(card_price)
    return {
        "list_price_brl": list_price_brl,
        "promotion": promotion,
        "price_brl": card_price,
        "pix_price_brl": pix_price,
        "pix_note": _PIX_NOTE if promotion else None,
        "installments": {"max": options[-1]["n"], "options": options},
        "combined_payment_allowed": card_price > COMBINED_PAYMENT_THRESHOLD_BRL,
    }
