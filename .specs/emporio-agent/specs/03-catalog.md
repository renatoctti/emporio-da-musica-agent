# Spec 03: Catalog search and product detail

**Status:** 🟡 Draft
**Author:** renatoctti
**Date:** 2026-10-31
**Scope:** product tools (search and detail)
**Depends on:** 01, 02
**Delivery:** autonomous (after its dependencies)

---

## Summary

Two tool functions over `StoreData`: `search_products` (filter, sort, limit) and `get_product`
(full detail with price quote, availability and alternatives). They encode the stock and status
rules of manual item 7.3.

## Context

"Which violões up to R$ 1000 are available?" and "How much is the Takamine GD20?" are the most
frequent questions. The model must never confirm availability without these tools (item 7.3).

---

## Allowed files

**Production**

- `src/emporio/catalog.py` (new)

**Tests**

- `tests/test_catalog.py` (new)

**Do not touch:** `data.py`, `pricing.py` (use them as they are).

---

## Functional requirements

| ID | Requirement | Priority | Acceptance criterion |
|---|---|---|---|
| 🟡 RF-01 | Availability is `in_stock` (active and stock above 0), `out_of_stock` (active, stock 0), `discontinued`, or `coming_soon`; `stock_quantity` is reported only for `in_stock` and is `None` otherwise (A9) | Must | Product 96 `out_of_stock`; 136 `discontinued` with `stock_quantity None`; 130 `coming_soon`; 81 `in_stock` with 12 |
| 🟡 RF-02 | The current promotion of a product is its **active** promotion with the highest discount (ties: highest promotion id); inactive promotions never change the price | Must | Product 121 current price 439.2; product 93 has no current promotion |
| 🟡 RF-03 | `search_products` filters by `query` (every normalized token must be a substring of the normalized name, category name, brand or reliable description; accents and case ignored), `category` (exact category name, accent- and case-insensitive), `min_price_brl`, `max_price_brl` (both against the **current** price), `string_type` (`nylon`/`steel`) and `electroacoustic` (bool, from `specs.electronics == "yes"`) | Must | "até R$ 1000" with category `Violões` returns only products whose current price is at most 1000 |
| 🟡 RF-04 | `available_only` defaults to true when `query` is empty and false when `query` is given, so a named product is found even when unavailable; an explicit value always wins | Must | `query="giannini gf-3d"` returns product 96 (out of stock); `category="Violões"` alone never returns 96, 113, 130 or 136 |
| 🟡 RF-05 | Results are sorted by current price ascending then name; `limit` defaults to 5, is capped at 10, and `limit < 1` returns `invalid_argument`; the response always carries `total_matches` | Must | 20 matches with limit 5 return 5 results and `total_matches == 20` |
| 🟡 RF-06 | An unknown `category` returns `unknown_category` listing the valid names | Must | `category="Pianos"` returns the error with 9 valid names |
| 🟡 RF-07 | A category that exists but has no products (ids 6, 7, 8) returns zero results and a note stating that nothing is registered for it | Must | `category="Instrumentos de Sopro (Madeiras)"` gives `results == []` and a non-empty `notes` |
| 🟡 RF-08 | `get_product(product_id)` returns the full record: name, brand, category, `description` (`None` plus `description_available: False` when unreliable), `specs`, availability, `price` (the `build_price_quote` dict) and `expired_promotions` (inactive ones, with percent and description) | Must | Product 135 has `description None`; product 93 lists 2 expired promotions |
| 🟡 RF-09 | `get_product` for a product that is not `in_stock` adds up to 3 `alternatives`: `in_stock` products of the same category, closest in price first | Must | Product 96 lists 3 in-stock violões, none with id 96 |
| 🟡 RF-10 | Unknown `product_id` returns `product_not_found` | Must | `get_product(9999)` returns that code |

---

## Expected behavior

### Search summary item

```
{"product_id": 121, "name": "Ohana CK-20 Concert Natural", "category": "Ukuleles",
 "list_price_brl": 549.0, "price_brl": 439.2,
 "promotion": {"description": "Desconto Exclusivo", "discount_percent": 20.0, "price_brl": 439.2} | None,
 "availability": "in_stock", "stock_quantity": 6, "string_type": "nylon" | "steel" | None,
 "electroacoustic": True | False | None}
```

`string_type` and `electroacoustic` come from `specs` when present, else `None`.

### Notes

`notes` is a list of short English hints for the model, for example "No product matched; do not
invent products." when `results` is empty, and the empty-category note of RF-07.

---

## Contracts

**`src/emporio/catalog.py`** 🟡

```python
def search_products(
    data: StoreData,
    *,
    query: str | None = None,
    category: str | None = None,
    min_price_brl: float | None = None,
    max_price_brl: float | None = None,
    string_type: Literal["nylon", "steel"] | None = None,
    electroacoustic: bool | None = None,
    available_only: bool | None = None,
    limit: int = 5,
) -> dict[str, Any]
# {"total_matches": int, "returned": int, "results": [summary...], "notes": [str, ...]}
# or {"error": {"code": "unknown_category" | "invalid_argument", "message": ...}}

def get_product(data: StoreData, product_id: int) -> dict[str, Any]
# {"found": True, "product_id", "name", "brand", "category", "description": str | None,
#  "description_available": bool, "specs": dict, "availability", "stock_quantity",
#  "price": <build_price_quote dict>, "expired_promotions": [...], "alternatives": [summary...]}
# or {"error": {"code": "product_not_found", ...}}
```

---

## Edge cases

| ID | Scenario | Trigger | Expected behavior |
|---|---|---|---|
| 🟡 EC-01 | Accent and case | `query="VIOLAO"` or `"violão"` | Both match descriptions containing "Violão" |
| 🟡 EC-02 | Partial model name | `query="takamine gd20"` | Matches product 95 only |
| 🟡 EC-03 | Price filter on promoted product | `max_price_brl=450` | Product 121 (current 439.2) is included although its list price is 549 |
| 🟡 EC-04 | Empty query and no filters | no arguments | Available products only, cheapest 5, `total_matches` is the available count |
| 🟡 EC-05 | `min_price_brl > max_price_brl` | 900 and 100 | `invalid_argument` |

---

## Minimum test cases

| # | Target | Scenario | Fixture | Expected result | Test file |
|---|---|---|---|---|---|
| 🟡 T-01 | availability | RF-01 ids | real `StoreData` | as listed | `tests/test_catalog.py` |
| 🟡 T-02 | promotion | RF-02 | real `StoreData` | as listed | `tests/test_catalog.py` |
| 🟡 T-03 | `search_products` | violões up to 1000 | real `StoreData` | only `Violões`, all `price_brl <= 1000`, ascending, none unavailable | `tests/test_catalog.py` |
| 🟡 T-04 | `search_products` | named unavailable product | `query="giannini gf-3d"` | product 96 `out_of_stock` | `tests/test_catalog.py` |
| 🟡 T-05 | `search_products` | limit and total | `limit=3` | 3 returned, total larger | `tests/test_catalog.py` |
| 🟡 T-06 | `search_products` | errors and empty category | `Pianos`, sopro, limit 0, min above max | codes and notes of RF-06, RF-07, EC-05 | `tests/test_catalog.py` |
| 🟡 T-07 | `search_products` | string type and electroacoustic | `steel`, `True` | only steel-string products with electronics yes | `tests/test_catalog.py` |
| 🟡 T-08 | `get_product` | detail, unreliable description, expired promotions | ids 121, 135, 93 | RF-08 | `tests/test_catalog.py` |
| 🟡 T-09 | `get_product` | alternatives and not found | ids 96, 9999 | RF-09, RF-10 | `tests/test_catalog.py` |

### Acceptance criterion

```bash
python -m pytest tests/test_catalog.py -q
```

---

## Implementation checklist

- [ ] 🟡 `git diff --stat` checked against **Allowed files**
- [ ] 🟡 Tests written before the code
- [ ] 🟡 Prices come from `pricing.build_price_quote`; no price arithmetic in this module
- [ ] 🟡 Business errors returned with `results.error`, never raised
- [ ] 🟡 Test fixtures use the real `data/` (field names identical to the contract)
- [ ] 🟡 `ruff check` and `ruff format --check` pass

## Open questions

None.

## Architectural adherence

| Rule | Status | Note |
|---|---|---|
| Domain modules do not import the LLM client | 🟡 | |
| No silent catch | 🟡 | |
| Scope respected | 🟡 | |