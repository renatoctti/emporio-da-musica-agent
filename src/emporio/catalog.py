"""Product tools: search and detail, with the availability rules of manual item 7.3."""

from __future__ import annotations

import unicodedata
from typing import Any

import pandas as pd

from emporio.data import StoreData
from emporio.pricing import build_price_quote
from emporio.results import error

DEFAULT_LIMIT = 5
MAX_LIMIT = 10
MAX_ALTERNATIVES = 3
STRING_TYPES = ("nylon", "steel")


def _normalize(text: str) -> str:
    """Lower-case without accents, so "VIOLÃO" and "violao" compare equal."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _availability(status: str, stock: int) -> str:
    if status in ("discontinued", "coming_soon"):
        return status
    return "in_stock" if stock > 0 else "out_of_stock"


def _current_promotion(data: StoreData, product_id: int) -> pd.Series | None:
    """The active promotion with the highest discount (ties: the newest one)."""
    promos = data.promotions
    active = promos[(promos.product_id == product_id) & promos.is_active]
    if active.empty:
        return None
    ranked = active.sort_values(["discount_percent", "promotion_id"], ascending=False)
    return ranked.iloc[0]


def _quote(data: StoreData, row: Any) -> dict[str, Any]:
    promo = _current_promotion(data, row.product_id)
    if promo is None:
        return build_price_quote(float(row.price_brl))
    return build_price_quote(
        float(row.price_brl), float(promo.discount_percent), str(promo.description)
    )


def _summary(row: Any, quote: dict[str, Any]) -> dict[str, Any]:
    availability = _availability(row.status, row.stock_quantity)
    strings = row.specs.get("strings")
    electronics = row.specs.get("electronics")
    return {
        "product_id": int(row.product_id),
        "name": row.name,
        "category": row.category_name,
        "list_price_brl": float(row.price_brl),
        "price_brl": quote["price_brl"],
        "promotion": quote["promotion"],
        "availability": availability,
        "stock_quantity": int(row.stock_quantity) if availability == "in_stock" else None,
        "string_type": strings if strings in STRING_TYPES else None,
        "electroacoustic": None if electronics is None else electronics == "yes",
    }


def _resolve_category(data: StoreData, category: str) -> str | None:
    wanted = _normalize(category.strip())
    for name in data.categories["name"]:
        if _normalize(name) == wanted:
            return name
    return None


def search_products(
    data: StoreData,
    *,
    query: str | None = None,
    category: str | None = None,
    min_price_brl: float | None = None,
    max_price_brl: float | None = None,
    string_type: str | None = None,
    electroacoustic: bool | None = None,
    available_only: bool | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    if limit < 1:
        return error("invalid_argument", "limit must be at least 1.")
    if string_type is not None and string_type not in STRING_TYPES:
        return error("invalid_argument", f"string_type must be one of {', '.join(STRING_TYPES)}.")
    if min_price_brl is not None and max_price_brl is not None and min_price_brl > max_price_brl:
        return error("invalid_argument", "min_price_brl is greater than max_price_brl.")

    category_name = None
    if category is not None:
        category_name = _resolve_category(data, category)
        if category_name is None:
            valid = ", ".join(data.categories["name"])
            return error("unknown_category", f"Unknown category {category!r}. Valid: {valid}.")

    tokens = _normalize(query).split() if query else []
    if available_only is None:
        # A named product must be found even when unavailable; a plain listing must not offer it.
        available_only = not tokens

    matches = []
    for row in data.products.itertuples():
        if category_name is not None and row.category_name != category_name:
            continue
        if available_only and _availability(row.status, row.stock_quantity) != "in_stock":
            continue
        if tokens:
            text = " ".join(
                p for p in (row.name, row.category_name, row.brand, row.description) if p
            )
            haystack = _normalize(text)
            if not all(token in haystack for token in tokens):
                continue
        quote = _quote(data, row)
        if min_price_brl is not None and quote["price_brl"] < min_price_brl:
            continue
        if max_price_brl is not None and quote["price_brl"] > max_price_brl:
            continue
        item = _summary(row, quote)
        if string_type is not None and item["string_type"] != string_type:
            continue
        if electroacoustic is not None and item["electroacoustic"] != electroacoustic:
            continue
        matches.append(item)

    matches.sort(key=lambda item: (item["price_brl"], item["name"]))
    results = matches[: min(limit, MAX_LIMIT)]

    notes = []
    if not matches:
        notes.append("No product matched; do not invent products.")
    if category_name is not None and not (data.products.category_name == category_name).any():
        notes.append(
            f"No products are registered for category {category_name}; "
            "do not say the store sells it."
        )
    return {
        "total_matches": len(matches),
        "returned": len(results),
        "results": results,
        "notes": notes,
    }


def get_product(data: StoreData, product_id: int) -> dict[str, Any]:
    found = data.products[data.products.product_id == product_id]
    if found.empty:
        return error("product_not_found", f"No product with id {product_id}.")
    row = next(found.itertuples())
    quote = _quote(data, row)
    summary = _summary(row, quote)

    promos = data.promotions
    expired = promos[(promos.product_id == product_id) & ~promos.is_active]

    alternatives: list[dict[str, Any]] = []
    if summary["availability"] != "in_stock":
        for other in data.products.itertuples():
            if other.product_id == product_id or other.category_id != row.category_id:
                continue
            if _availability(other.status, other.stock_quantity) != "in_stock":
                continue
            alternatives.append(_summary(other, _quote(data, other)))
        alternatives.sort(key=lambda a: (abs(a["price_brl"] - summary["price_brl"]), a["name"]))
        alternatives = alternatives[:MAX_ALTERNATIVES]

    return {
        "found": True,
        "product_id": summary["product_id"],
        "name": row.name,
        "brand": row.brand,
        "category": row.category_name,
        "description": row.description,
        "description_available": bool(row.description_reliable),
        "specs": row.specs,
        "availability": summary["availability"],
        "stock_quantity": summary["stock_quantity"],
        "price": quote,
        "expired_promotions": [
            {"description": str(p.description), "discount_percent": float(p.discount_percent)}
            for p in expired.itertuples()
        ],
        "alternatives": alternatives,
    }
