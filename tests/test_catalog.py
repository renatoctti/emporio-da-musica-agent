from pathlib import Path

import pytest

from emporio.catalog import get_product, search_products
from emporio.data import load_store_data
from emporio.results import is_error

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def data():
    return load_store_data(DATA_DIR)


def ids(result):
    return [r["product_id"] for r in result["results"]]


def test_availability_rules(data):
    cases = {
        96: ("out_of_stock", None),
        136: ("discontinued", None),
        130: ("coming_soon", None),
        81: ("in_stock", 12),
    }
    for pid, (availability, stock) in cases.items():
        p = get_product(data, pid)
        assert (p["availability"], p["stock_quantity"]) == (availability, stock), pid


def test_current_promotion_is_the_active_one(data):
    assert get_product(data, 121)["price"]["price_brl"] == 439.2
    p93 = get_product(data, 93)
    assert p93["price"]["promotion"] is None
    assert p93["price"]["price_brl"] == 11499.0
    assert len(p93["expired_promotions"]) == 2
    assert {e["discount_percent"] for e in p93["expired_promotions"]} == {15.0, 10.0}


def test_violoes_up_to_1000_only_lists_available_ones_by_price(data):
    r = search_products(data, category="Violões", max_price_brl=1000)
    products = data.products
    expected = products[
        (products.category_id == 5)
        & (products.status == "active")
        & (products.stock_quantity > 0)
        & (products.price_brl <= 1000)
    ]
    assert r["total_matches"] == len(expected)
    prices = [x["price_brl"] for x in r["results"]]
    assert prices == sorted(prices) and all(p <= 1000 for p in prices)
    assert {x["category"] for x in r["results"]} == {"Violões"}
    assert {x["availability"] for x in r["results"]} == {"in_stock"}
    assert not {96, 113, 130, 136} & set(ids(r))


def test_named_unavailable_product_is_still_found(data):
    r = search_products(data, query="giannini gf-3d")
    assert ids(r) == [96]
    assert r["results"][0]["availability"] == "out_of_stock"


def test_listing_by_category_never_returns_unavailable_products(data):
    r = search_products(data, category="Violões", limit=10)
    assert not {96, 113, 130, 136} & set(ids(r))


def test_explicit_available_only_wins(data):
    r = search_products(data, query="giannini gf-3d", available_only=True)
    assert r["results"] == []


def test_limit_and_total(data):
    r = search_products(data, category="Violões", limit=3)
    assert r["returned"] == 3 and len(r["results"]) == 3
    assert r["total_matches"] > 3
    assert search_products(data, category="Violões", limit=99)["returned"] == 10


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"category": "Pianos"}, "unknown_category"),
        ({"limit": 0}, "invalid_argument"),
        ({"min_price_brl": 900, "max_price_brl": 100}, "invalid_argument"),
        ({"string_type": "gut"}, "invalid_argument"),
    ],
)
def test_invalid_arguments(data, kwargs, code):
    r = search_products(data, **kwargs)
    assert is_error(r) and r["error"]["code"] == code


def test_unknown_category_lists_the_valid_names(data):
    message = search_products(data, category="Pianos")["error"]["message"]
    for name in data.categories["name"]:
        assert name in message


def test_empty_category_explains_that_nothing_is_registered(data):
    r = search_products(data, category="Instrumentos de Sopro (Madeiras)")
    assert r["results"] == [] and r["total_matches"] == 0
    assert any("no products" in n.lower() for n in r["notes"])


def test_no_match_note(data):
    r = search_products(data, query="theremin")
    assert r["results"] == [] and any("invent" in n for n in r["notes"])


def test_string_type_and_electroacoustic_filters(data):
    r = search_products(data, category="Violões", string_type="steel", electroacoustic=True)
    assert r["results"]
    assert {x["string_type"] for x in r["results"]} == {"steel"}
    assert {x["electroacoustic"] for x in r["results"]} == {True}


def test_accents_and_case_are_ignored(data):
    a = ids(search_products(data, query="VIOLAO", limit=10))
    b = ids(search_products(data, query="violão", limit=10))
    assert a == b and a


def test_partial_model_name(data):
    assert ids(search_products(data, query="takamine gd20")) == [95]


def test_price_filter_uses_the_promotional_price(data):
    r = search_products(data, category="Ukuleles", max_price_brl=450, limit=10)
    assert 121 in ids(r)
    item = next(x for x in r["results"] if x["product_id"] == 121)
    assert item["list_price_brl"] == 549.0 and item["price_brl"] == 439.2
    assert item["promotion"]["discount_percent"] == 20.0


def test_search_without_filters_lists_the_cheapest_available(data):
    r = search_products(data)
    products = data.products
    available = products[(products.status == "active") & (products.stock_quantity > 0)]
    assert r["total_matches"] == len(available)
    assert r["returned"] == 5
    assert r["results"][0]["price_brl"] == available.price_brl.min()


def test_product_detail(data):
    p = get_product(data, 121)
    assert p["found"] is True
    assert p["name"] == "Ohana CK-20 Concert Natural"
    assert p["brand"] == "Ohana" and p["category"] == "Ukuleles"
    assert p["description_available"] is True and p["description"]
    assert p["specs"]["strings"] == "nylon"
    assert p["alternatives"] == []
    assert p["price"]["installments"]["max"] == 5


def test_unreliable_description_is_not_exposed(data):
    p = get_product(data, 135)
    assert p["description"] is None and p["description_available"] is False


def test_alternatives_for_unavailable_products(data):
    p = get_product(data, 96)
    alts = p["alternatives"]
    assert len(alts) == 3
    assert all(a["availability"] == "in_stock" and a["category"] == "Violões" for a in alts)
    assert 96 not in [a["product_id"] for a in alts]
    gaps = [abs(a["price_brl"] - 799.9) for a in alts]
    assert gaps == sorted(gaps)


def test_unknown_product(data):
    r = get_product(data, 9999)
    assert is_error(r) and r["error"]["code"] == "product_not_found"
