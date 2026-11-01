"""Loads the store CSVs into typed tables, cleans the known traps and reports data issues."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

FILE_TEMPLATE = "desafio_tecnico_ai_eng - {name}.csv"

KNOWN_BRANDS: tuple[str, ...] = (
    "Yamaha",
    "Tagima",
    "Giannini",
    "Rozini",
    "Shelby",
    "Crafter",
    "Martin",
    "Taylor",
    "Takamine",
    "Kala",
    "Ohana",
    "Kalani",
    "Fender",
    "Gibson",
    "Ibanez",
    "PRS",
    "Music Man",
    "Korg",
    "Nord",
    "Roland",
    "Pearl",
    "Tama",
)
_BRAND_PATTERNS = {
    brand: re.compile(rf"\b{re.escape(brand)}\b")
    for brand in sorted(KNOWN_BRANDS, key=len, reverse=True)
}
_STRING_COUNT = re.compile(r"(\d+)\s*cordas", re.IGNORECASE)
_KEY_COUNT = re.compile(r"(\d+)\s*teclas", re.IGNORECASE)
_CREDIT = re.compile(r"credit_(\d+)x")
_TOTAL_TOLERANCE_BRL = 0.01


@dataclass(frozen=True)
class DataIssue:
    kind: str
    subject: str
    detail: str


@dataclass(frozen=True)
class StoreData:
    categories: pd.DataFrame
    products: pd.DataFrame
    promotions: pd.DataFrame
    customers: pd.DataFrame
    orders: pd.DataFrame
    order_items: pd.DataFrame
    issues: tuple[DataIssue, ...]


def _read_csv(data_dir: Path, name: str) -> list[dict[str, str]]:
    path = data_dir / FILE_TEMPLATE.format(name=name)
    if not path.is_file():
        raise FileNotFoundError(f"Missing data file: {path.name} (looked in {data_dir})")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    return frame.to_dict("records")


def _frame(records: list[dict[str, Any]], columns: list[str], optional: tuple[str, ...] = ()):
    """DataFrame whose optional columns keep real `None`s (pandas would turn them into NaN)."""
    frame = pd.DataFrame(records, columns=columns)
    for name in optional:
        frame[name] = pd.Series([r[name] for r in records], dtype="object", index=frame.index)
    return frame


def _brand_in(text: str) -> str | None:
    for brand, pattern in _BRAND_PATTERNS.items():
        if pattern.search(text):
            return brand
    return None


def _brands_in(text: str) -> list[str]:
    return [brand for brand, pattern in _BRAND_PATTERNS.items() if pattern.search(text)]


def _count_mismatch(description: str, pattern: re.Pattern[str], spec_value: Any) -> str | None:
    """Describe a contradiction between "N cordas/teclas" in the text and a numeric spec."""
    match = pattern.search(description)
    if match is None or not str(spec_value).isdigit():
        return None
    if int(match.group(1)) == int(spec_value):
        return None
    return f"description says {match.group(1)}, specs say {spec_value}"


def _clean_products(rows, categories, issues: list[DataIssue]) -> pd.DataFrame:
    category_names = {int(r["category_id"]): r["name"] for r in categories}
    records = []
    for row in rows:
        pid = int(row["product_id"])
        try:
            specs = json.loads(row["specs"])
        except json.JSONDecodeError as exc:
            raise ValueError(f"product {pid}: invalid specs JSON ({exc})") from exc
        name = row["name"]
        brand = _brand_in(name)
        description = row["description"]

        reliable = True
        foreign = [b for b in _brands_in(description) if b != brand]
        if foreign:
            reliable = False
            issues.append(
                DataIssue(
                    "description_brand_mismatch",
                    f"product {pid}",
                    f"name has {brand}, description mentions {', '.join(foreign)}",
                )
            )
        for pattern, key in ((_STRING_COUNT, "strings"), (_KEY_COUNT, "keys")):
            problem = _count_mismatch(description, pattern, specs.get(key))
            if problem:
                reliable = False
                issues.append(DataIssue("description_spec_mismatch", f"product {pid}", problem))

        records.append(
            {
                "product_id": pid,
                "name": name,
                "category_id": int(row["category_id"]),
                "category_name": category_names[int(row["category_id"])],
                "brand": brand,
                "price_brl": float(row["price_brl"]),
                "stock_quantity": int(row["stock_quantity"]),
                "status": row["status"],
                "description": description if reliable else None,
                "description_reliable": reliable,
                "specs": specs,
                "created_at": date.fromisoformat(row["created_at"]),
            }
        )
    columns = list(records[0])
    return _frame(records, columns, optional=("brand", "description"))


def _clean_orders(rows) -> pd.DataFrame:
    records = []
    for row in rows:
        credit = _CREDIT.fullmatch(row["payment_method"])
        eta = row["estimated_delivery"]
        records.append(
            {
                "order_id": int(row["order_id"]),
                "customer_id": int(row["customer_id"]),
                "order_date": date.fromisoformat(row["order_date"]),
                "status": row["status"],
                "total_brl": float(row["total_brl"]),
                "payment_method": row["payment_method"],
                "payment_kind": "credit" if credit else row["payment_method"],
                "installments": int(credit.group(1)) if credit else None,
                "tracking_code": row["tracking_code"] or None,
                "estimated_delivery": date.fromisoformat(eta) if eta else None,
                "notes": row["notes"] or None,
            }
        )
    return _frame(
        records,
        list(records[0]),
        optional=("installments", "tracking_code", "estimated_delivery", "notes"),
    )


def _clean_customers(rows) -> pd.DataFrame:
    records = []
    for row in rows:
        digits = re.sub(r"\D", "", row["phone"])
        if digits.startswith("55") and len(digits) > 11:
            digits = digits[2:]
        records.append(
            {
                "customer_id": int(row["customer_id"]),
                "name": row["name"],
                "phone": row["phone"],
                "phone_digits": digits,
                "email": row["email"],
                "email_norm": row["email"].strip().lower(),
                "city": row["city"],
            }
        )
    return _frame(records, list(records[0]))


def _collect_issues(products, promotions, customers, orders, order_items, categories, issues):
    prices = dict(zip(products.product_id, products.price_brl, strict=True))
    for order_id, group in order_items.groupby("order_id"):
        item_sum = sum(prices[r.product_id] * r.quantity for r in group.itertuples())
        total = float(orders.loc[orders.order_id == order_id, "total_brl"].iloc[0])
        if abs(item_sum - total) > _TOTAL_TOLERANCE_BRL:
            issues.append(
                DataIssue(
                    "order_total_mismatch",
                    f"order {order_id}",
                    f"recorded total {total:.2f}, item prices sum to {item_sum:.2f}",
                )
            )

    ordered = set(order_items.product_id)
    for p in products.itertuples():
        if p.status == "discontinued" and p.stock_quantity > 0:
            issues.append(
                DataIssue(
                    "status_stock_conflict",
                    f"product {p.product_id}",
                    f"discontinued but stock is {p.stock_quantity}",
                )
            )
        if p.status == "coming_soon" and p.product_id in ordered:
            issues.append(
                DataIssue(
                    "status_stock_conflict",
                    f"product {p.product_id}",
                    "coming_soon but present in existing orders",
                )
            )

    for email, group in customers.groupby("email_norm"):
        if len(group) > 1:
            ids = ",".join(str(i) for i in sorted(group.customer_id))
            issues.append(DataIssue("duplicate_email", f"customers {ids}", f"share {email}"))

    for c in categories.itertuples():
        if not (products.category_id == c.category_id).any():
            issues.append(
                DataIssue(
                    "empty_category", f"category {c.category_id}", f"{c.name} has no products"
                )
            )

    for product_id, group in promotions.groupby("product_id"):
        if len(group) > 1:
            issues.append(
                DataIssue(
                    "multiple_promotions",
                    f"product {product_id}",
                    f"{len(group)} promotions, {int(group.is_active.sum())} active",
                )
            )


def load_store_data(data_dir: Path) -> StoreData:
    data_dir = Path(data_dir)
    category_rows = _read_csv(data_dir, "categories")
    product_rows = _read_csv(data_dir, "products")
    promotion_rows = _read_csv(data_dir, "promotions")
    customer_rows = _read_csv(data_dir, "customers")
    order_rows = _read_csv(data_dir, "orders")
    item_rows = _read_csv(data_dir, "order_items")

    issues: list[DataIssue] = []
    categories = _frame(
        [
            {
                "category_id": int(r["category_id"]),
                "name": r["name"],
                "description": r["description"],
            }
            for r in category_rows
        ],
        ["category_id", "name", "description"],
    )
    products = _clean_products(product_rows, category_rows, issues)
    promotions = _frame(
        [
            {
                "promotion_id": int(r["promotion_id"]),
                "product_id": int(r["product_id"]),
                "discount_percent": float(r["discount_percent"]),
                "description": r["description"],
                "is_active": r["is_active"] == "1",
            }
            for r in promotion_rows
        ],
        ["promotion_id", "product_id", "discount_percent", "description", "is_active"],
    )
    customers = _clean_customers(customer_rows)
    orders = _clean_orders(order_rows)
    order_items = _frame(
        [
            {
                "order_id": int(r["order_id"]),
                "product_id": int(r["product_id"]),
                "quantity": int(r["quantity"]),
            }
            for r in item_rows
        ],
        ["order_id", "product_id", "quantity"],
    )

    _collect_issues(products, promotions, customers, orders, order_items, categories, issues)
    return StoreData(
        categories=categories,
        products=products,
        promotions=promotions,
        customers=customers,
        orders=orders,
        order_items=order_items,
        issues=tuple(sorted(issues, key=lambda i: (i.kind, i.subject))),
    )
