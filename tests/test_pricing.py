import pytest

from emporio.pricing import (
    COMBINED_PAYMENT_THRESHOLD_BRL,
    MAX_INSTALLMENTS,
    PIX_DISCOUNT_PERCENT,
    build_price_quote,
    min_installment_brl,
)


def options(quote):
    return {o["n"]: o["installment_brl"] for o in quote["installments"]["options"]}


def test_constants_follow_the_manual():
    assert PIX_DISCOUNT_PERCENT == 5.0
    assert COMBINED_PAYMENT_THRESHOLD_BRL == 2000.0
    assert MAX_INSTALLMENTS == 12


def test_promotion_blocks_pix_and_limits_installments():
    q = build_price_quote(549.0, 20, "Desconto Exclusivo")
    assert q["list_price_brl"] == 549.0
    assert q["promotion"] == {
        "description": "Desconto Exclusivo",
        "discount_percent": 20.0,
        "price_brl": 439.2,
    }
    assert q["price_brl"] == 439.2
    assert q["pix_price_brl"] is None
    assert "stack" in q["pix_note"]
    assert q["installments"]["max"] == 5
    assert options(q) == {1: 439.2, 2: 219.6, 3: 146.4, 4: 109.8, 5: 87.84}
    assert q["combined_payment_allowed"] is False


def test_no_promotion_gives_pix_and_full_installments():
    q = build_price_quote(11499.0)
    assert q["promotion"] is None
    assert q["price_brl"] == 11499.0
    assert q["pix_price_brl"] == 10924.05
    assert q["pix_note"] is None
    assert q["installments"]["max"] == 12
    assert options(q)[12] == 958.25
    assert q["combined_payment_allowed"] is True


def test_installments_use_the_card_price_not_the_pix_price():
    q = build_price_quote(1000.0)
    assert options(q)[1] == 1000.0


@pytest.mark.parametrize(
    ("price", "expected_max"),
    [
        (49.9, 1),
        (99.0, 1),
        (100.0, 2),
        (150.0, 3),
        (319.9, 3),
        (320.0, 4),
        (700.0, 7),
        (19567.0, 12),
    ],
)
def test_maximum_installments_at_the_boundaries(price, expected_max):
    assert build_price_quote(price)["installments"]["max"] == expected_max


def test_options_are_contiguous_and_start_at_one():
    for price in (49.9, 150.0, 439.2, 5999.0):
        ns = [o["n"] for o in build_price_quote(price)["installments"]["options"]]
        assert ns == list(range(1, len(ns) + 1))


@pytest.mark.parametrize(
    ("n", "minimum"),
    [(1, 0.0), (2, 50.0), (3, 50.0), (4, 80.0), (6, 80.0), (7, 100.0), (12, 100.0)],
)
def test_min_installment(n, minimum):
    assert min_installment_brl(n) == minimum


@pytest.mark.parametrize("n", [0, 13, -1])
def test_min_installment_rejects_out_of_range(n):
    with pytest.raises(ValueError):
        min_installment_brl(n)


@pytest.mark.parametrize(
    "args", [(0.0,), (-5.0,), (100.0, 0.0), (100.0, 100.0), (100.0, -1.0), (100.0, 120.0)]
)
def test_invalid_inputs_raise(args):
    with pytest.raises(ValueError):
        build_price_quote(*args)


def test_combined_payment_threshold_is_strictly_above():
    assert build_price_quote(2000.0)["combined_payment_allowed"] is False
    assert build_price_quote(2000.01)["combined_payment_allowed"] is True
