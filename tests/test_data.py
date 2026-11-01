import json
import shutil
from pathlib import Path

import pytest

from emporio.data import KNOWN_BRANDS, load_store_data

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def data():
    return load_store_data(DATA_DIR)


def product(data, product_id):
    return data.products[data.products.product_id == product_id].iloc[0]


def order(data, order_id):
    return data.orders[data.orders.order_id == order_id].iloc[0]


def test_row_counts_and_types(data):
    assert len(data.categories) == 9
    assert len(data.products) == 65
    assert len(data.promotions) == 25
    assert len(data.customers) == 50
    assert len(data.orders) == 20
    assert len(data.order_items) == 22
    p = product(data, 81)
    assert p["price_brl"] == 599.9
    assert p["stock_quantity"] == 12
    assert isinstance(p["specs"], dict) and p["specs"]["strings"] == "nylon"
    assert p["category_name"] == "Violões"


def test_missing_file_names_the_file(tmp_path):
    for f in DATA_DIR.glob("*.csv"):
        if "orders" not in f.name or "order_items" in f.name:
            shutil.copy(f, tmp_path / f.name)
    with pytest.raises(FileNotFoundError, match="orders"):
        load_store_data(tmp_path)


def test_invalid_specs_json_names_the_product(tmp_path):
    for f in DATA_DIR.glob("*.csv"):
        shutil.copy(f, tmp_path / f.name)
    target = tmp_path / "desafio_tecnico_ai_eng - products.csv"
    target.write_text(
        target.read_text(encoding="utf-8").replace('{""top"":""Spruce"",', "{not json,", 1),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="product 8"):
        load_store_data(tmp_path)


def test_brands_are_detected_on_whole_words(data):
    assert data.products["brand"].notna().all()
    assert set(data.products["brand"]) <= set(KNOWN_BRANDS)
    assert product(data, 120)["brand"] == "Kala"
    assert product(data, 118)["brand"] == "Kalani"
    assert product(data, 135)["brand"] == "Music Man"


def test_unreliable_descriptions_are_exactly_the_known_ids(data):
    unreliable = set(data.products.loc[~data.products.description_reliable, "product_id"])
    assert unreliable == {135, 137, 139, 140, 142, 144}
    for pid in unreliable:
        assert product(data, pid)["description"] is None
    assert product(data, 131)["description"].startswith("Guitarra elétrica Gibson")
    assert product(data, 81)["description_reliable"]


def test_derived_columns(data):
    o2 = order(data, 2)
    assert (o2["payment_kind"], o2["installments"]) == ("credit", 6)
    assert order(data, 1)["payment_kind"] == "pix"
    assert order(data, 1)["installments"] is None
    o9 = order(data, 9)
    assert o9["tracking_code"] is None
    assert o9["estimated_delivery"] is None
    assert o9["notes"] is None
    assert order(data, 17)["notes"].startswith("Pedido cancelado")
    c1 = data.customers[data.customers.customer_id == 1].iloc[0]
    assert c1["phone_digits"] == "67998123456"
    assert c1["email_norm"] == "lucas.mendes@jmail.com"
    active = data.promotions[data.promotions.is_active]
    assert sorted(active.promotion_id) == [12, 14, 19, 24]


def test_issues_on_real_data(data):
    by_kind = {}
    for issue in data.issues:
        by_kind.setdefault(issue.kind, []).append(issue)
    assert {i.subject for i in by_kind["order_total_mismatch"]} == {"order 3", "order 20"}
    assert "customers 11,43" in {i.subject for i in by_kind["duplicate_email"]}
    assert {i.subject for i in by_kind["empty_category"]} == {
        "category 6",
        "category 7",
        "category 8",
    }
    conflicts = {i.subject for i in by_kind["status_stock_conflict"]}
    assert {"product 136", "product 130"} <= conflicts
    brand = {i.subject for i in by_kind["description_brand_mismatch"]}
    assert brand == {f"product {n}" for n in (135, 137, 139, 140, 142, 144)}
    spec = {i.subject for i in by_kind["description_spec_mismatch"]}
    assert {"product 137", "product 142"} <= spec
    multi = {i.subject for i in by_kind["multiple_promotions"]}
    assert multi == {"product 93", "product 96", "product 99"}
    json.dumps([i.detail for i in data.issues])
