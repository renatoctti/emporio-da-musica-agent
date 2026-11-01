# Spec 01: Foundation, settings and data

**Status:** 🟡 Draft
**Author:** renatoctti
**Date:** 2026-10-31
**Scope:** configuration, error helper, CSV loading and cleaning
**Depends on:** none
**Delivery:** autonomous

---

## Summary

Creates the settings object, the shared error/rounding helpers and the loader that reads the six
store CSVs into typed, cleaned tables together with a list of data-quality issues. Every other
spec reads data only through `StoreData`.

## Context

The raw CSVs contain deliberate traps (see `overview.md`, "Contracts and schemas"). Cleaning them
once at load time keeps every tool simple and makes the decisions visible and testable.

---

## Allowed files

**Production**

- `src/emporio/config.py` (new): `Settings`, `load_settings`, `ConfigError`
- `src/emporio/results.py` (new): `error`, `is_error`, `round_brl`
- `src/emporio/data.py` (new): `StoreData`, `DataIssue`, `load_store_data`, `KNOWN_BRANDS`
- `.env.example`: document the variables and defaults
- `.gitignore`: add `var/`

**Tests**

- `tests/test_config.py` (new)
- `tests/test_results.py` (new)
- `tests/test_data.py` (new)

**Do not touch:** every other file in `src/emporio/`.

---

## Functional requirements

| ID | Requirement | Priority | Acceptance criterion |
|---|---|---|---|
| 🟡 RF-01 | `load_settings` reads `EMPORIO_DATA_DIR`, `EMPORIO_DB_PATH`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `EMPORIO_TODAY` from a mapping (default: `os.environ` after loading `.env`) | Must | With an empty mapping the defaults are `data/` next to the repo root, `var/emporio.db`, `https://openrouter.ai/api/v1`, no API key, model `anthropic/claude-haiku-5.5`, `today` equal to the system date |
| 🟡 RF-02 | Empty-string values count as unset | Must | `{"LLM_MODEL": ""}` yields the default model (`.env.example` ships empty values) |
| 🟡 RF-03 | `EMPORIO_TODAY=YYYY-MM-DD` fixes `today` and sets `now` to that date at 10:00; otherwise `now` is the system clock | Must | `EMPORIO_TODAY=2026-03-25` gives `today == date(2026, 3, 25)` and `now == datetime(2026, 3, 25, 10, 0)` |
| 🟡 RF-04 | An invalid `EMPORIO_TODAY` raises `ConfigError` naming the variable | Must | `EMPORIO_TODAY=25/03/2026` raises with "EMPORIO_TODAY" in the message |
| 🟡 RF-05 | `results.error(code, message)` returns `{"error": {"code", "message"}}`; `is_error` detects it | Must | Round trip on both helpers |
| 🟡 RF-06 | `round_brl` rounds half-up to 2 decimals using decimal arithmetic | Must | `round_brl(0.125) == 0.13`, `round_brl(2.675) == 2.68`, `round_brl(439.2) == 439.2` |
| 🟡 RF-07 | `load_store_data(data_dir)` reads the six CSVs (`desafio_tecnico_ai_eng - <name>.csv`) as UTF-8 into DataFrames with typed columns (see Contracts) | Must | Row counts 9, 65, 25, 50, 20, 22 for categories, products, promotions, customers, orders, order_items |
| 🟡 RF-08 | A missing CSV raises `FileNotFoundError` naming the file; invalid `specs` JSON raises `ValueError` naming the product id | Must | Both cases covered with a temporary data dir |
| 🟡 RF-09 | Each product gets `category_name`, `brand` (first known brand found as a whole word in the name, longest brand first, else `None`) and `specs` as a dict | Must | Every one of the 65 products has a brand; product 120 is `Kala`, product 118 is `Kalani`, product 135 is `Music Man` |
| 🟡 RF-10 | A description is **unreliable** when it names a known brand different from the product's brand, or when `N cordas` / `N teclas` in the description differs from a numeric `specs.strings` / `specs.keys`. Unreliable descriptions become `None` and `description_reliable` is `False` | Must | The unreliable ids on the real data are exactly {135, 137, 139, 140, 142, 144}; every other product keeps its description |
| 🟡 RF-11 | Promotions get a boolean `is_active`; customers get `email_norm` (stripped, lower-case) and `phone_digits` (digits only, leading `55` removed); orders get `payment_kind` (`pix`, `debit`, `boleto`, `credit`), `installments` (int or `None`), and `None` for empty `tracking_code`, `estimated_delivery`, `notes` | Must | Order 2 gives `payment_kind == "credit"`, `installments == 6`; order 9 has `tracking_code is None`; customer 1 has `phone_digits == "67998123456"` |
| 🟡 RF-12 | `StoreData.issues` lists `DataIssue(kind, subject, detail)` for: `description_brand_mismatch`, `description_spec_mismatch`, `order_total_mismatch` (item sum from current product prices differs from `total_brl` by more than R$ 0.01), `status_stock_conflict` (discontinued with stock above zero, or coming_soon product present in orders), `duplicate_email`, `empty_category`, `multiple_promotions` | Must | On the real data: `order_total_mismatch` subjects are exactly orders 3 and 20; `duplicate_email` covers customers 11 and 43; `empty_category` covers categories 6, 7, 8; `status_stock_conflict` includes products 136 and 130 |

---

## Expected behavior

### Main flow

1. `load_settings()` resolves paths relative to the repository root (two levels above `config.py`) unless overridden.
2. `load_store_data(settings.data_dir)` reads each CSV with all columns as strings, converts types, applies RF-09 to RF-12, and returns an immutable `StoreData`.
3. Nothing is written to disk.

### Alternative flows

**A: dotenv.** When `load_settings` is called without an explicit mapping it first calls `dotenv.load_dotenv()` (no override of real environment variables). With an explicit mapping, `.env` is not read (keeps tests hermetic).

---

## Contracts

**`src/emporio/config.py`** 🟡

```python
@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    llm_base_url: str
    llm_api_key: str | None
    llm_model: str
    now: datetime
    today: date

class ConfigError(ValueError): ...

def load_settings(env: Mapping[str, str] | None = None) -> Settings
```

**`src/emporio/results.py`** 🟡

```python
def error(code: str, message: str) -> dict[str, dict[str, str]]
def is_error(result: Mapping[str, Any]) -> bool
def round_brl(value: float) -> float
```

**`src/emporio/data.py`** 🟡

```python
KNOWN_BRANDS: tuple[str, ...]   # Yamaha Tagima Giannini Rozini Shelby Crafter Martin Taylor Takamine
                                # Kala Ohana Kalani Fender Gibson Ibanez PRS "Music Man" Korg Nord
                                # Roland Pearl Tama

@dataclass(frozen=True)
class DataIssue:
    kind: str
    subject: str     # e.g. "product 137", "order 3", "customers 11,43"
    detail: str

@dataclass(frozen=True)
class StoreData:
    categories: pd.DataFrame     # category_id:int, name, description
    products: pd.DataFrame       # product_id:int, name, category_id:int, category_name, brand, price_brl:float,
                                 # stock_quantity:int, status, description:str|None, description_reliable:bool,
                                 # specs:dict, created_at:date
    promotions: pd.DataFrame     # promotion_id:int, product_id:int, discount_percent:float, description, is_active:bool
    customers: pd.DataFrame      # customer_id:int, name, phone, phone_digits, email, email_norm, city
    orders: pd.DataFrame         # order_id:int, customer_id:int, order_date:date, status, total_brl:float,
                                 # payment_method, payment_kind, installments:int|None, tracking_code:str|None,
                                 # estimated_delivery:date|None, notes:str|None
    order_items: pd.DataFrame    # order_id:int, product_id:int, quantity:int
    issues: tuple[DataIssue, ...]

def load_store_data(data_dir: Path) -> StoreData
```

Errors: `FileNotFoundError` (missing CSV), `ValueError` (invalid specs JSON). No silent fallbacks.

---

## Edge cases

| ID | Scenario | Trigger | Expected behavior |
|---|---|---|---|
| 🟡 EC-01 | Brand is a prefix of another brand | `Kala` and `Kalani` | Whole-word match; `Kalani KAL-300S` gets `Kalani` |
| 🟡 EC-02 | Description mentions its own brand | product 131 (Gibson, description names Gibson) | Description kept, no issue |
| 🟡 EC-03 | `specs.strings` is `nylon` (not numeric) | violões | No numeric comparison, description kept |
| 🟡 EC-04 | Empty CSV cell in dates and codes | orders 9 to 20 | Value is `None`, never `""` or `NaN` |

---

## Minimum test cases

| # | Target | Scenario | Fixture | Expected result | Test file |
|---|---|---|---|---|---|
| 🟡 T-01 | `load_settings` | defaults | `{}` | RF-01 values | `tests/test_config.py` |
| 🟡 T-02 | `load_settings` | empty strings and fixed today | `{"LLM_MODEL": "", "EMPORIO_TODAY": "2026-03-25"}` | default model, fixed `now` | `tests/test_config.py` |
| 🟡 T-03 | `load_settings` | invalid date | `{"EMPORIO_TODAY": "x"}` | `ConfigError` mentioning the variable | `tests/test_config.py` |
| 🟡 T-04 | `round_brl`, `error`, `is_error` | values from RF-05 and RF-06 | n/a | as listed | `tests/test_results.py` |
| 🟡 T-05 | `load_store_data` | real data counts and typed columns | real `data/` | counts of RF-07 | `tests/test_data.py` |
| 🟡 T-06 | `load_store_data` | missing file and bad specs | tmp dir copy with one file removed or corrupted | the errors of RF-08 | `tests/test_data.py` |
| 🟡 T-07 | brands and descriptions | RF-09 and RF-10 on real data | real `data/` | the sets listed | `tests/test_data.py` |
| 🟡 T-08 | derived columns | RF-11 examples | real `data/` | as listed | `tests/test_data.py` |
| 🟡 T-09 | `issues` | RF-12 on real data | real `data/` | subjects listed | `tests/test_data.py` |

### Acceptance criterion

```bash
python -m pytest tests/test_config.py tests/test_results.py tests/test_data.py -q
```

---

## Implementation checklist

- [ ] 🟡 `git diff --stat` checked against **Allowed files**
- [ ] 🟡 Tests written before the code
- [ ] 🟡 Type hints on every public function; no `Any` except for JSON-like dicts
- [ ] 🟡 Fail fast: no `except` that swallows errors
- [ ] 🟡 `ruff check` and `ruff format --check` pass

## Open questions

None.

## Architectural adherence

| Rule | Status | Note |
|---|---|---|
| Tools and data modules do not import the LLM client | 🟡 | `data.py` imports only pandas and stdlib |
| No silent catch | 🟡 | |
| Scope respected | 🟡 | |