from datetime import date
from pathlib import Path

import pytest

from emporio.data import load_store_data
from emporio.results import is_error
from emporio.returns import check_return_eligibility
from emporio.session import SessionState

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
# Order 7: customer 14, bought 2026-02-03, estimated delivery (receipt) 2026-02-17.
RECEIVED = date(2026, 2, 17)


@pytest.fixture(scope="module")
def data():
    return load_store_data(DATA_DIR)


def verified(customer_id):
    return SessionState(verified_customer_id=customer_id)


def check(data, order_id, reason, today, customer=14):
    return check_return_eligibility(data, verified(customer), order_id, reason, today)


@pytest.mark.parametrize(
    ("customer", "order", "code"),
    [(15, 17, "order_cancelled"), (2, 8, "not_received_yet"), (16, 12, "not_shipped_yet")],
)
def test_orders_that_were_not_delivered_are_not_eligible(data, customer, order, code):
    result = check(data, order, "regret", date(2026, 3, 25), customer)
    assert result["eligible"] is False and result["reason_code"] == code
    assert result["route"] is None and result["days_since_receipt"] is None


def test_delivered_order_whose_receipt_is_in_the_future_is_not_received_yet(data):
    result = check(data, 7, "regret", date(2026, 2, 10))
    assert result["eligible"] is False and result["reason_code"] == "not_received_yet"
    assert result["received_on"] == "2026-02-17"


@pytest.mark.parametrize("reason", ["regret", "preference"])
@pytest.mark.parametrize(
    ("today", "eligible", "days"),
    [
        (date(2026, 2, 17), True, 0),
        (date(2026, 2, 19), True, 2),
        (date(2026, 2, 24), True, 7),
        (date(2026, 2, 25), False, 8),
    ],
)
def test_seven_day_windows_from_receipt(data, reason, today, eligible, days):
    result = check(data, 7, reason, today)
    assert result["eligible"] is eligible
    assert result["days_since_receipt"] == days
    assert result["received_on"] == "2026-02-17"
    assert result["deadline"] == "2026-02-24"
    if eligible:
        assert result["reason_code"] == "ok"
    else:
        assert result["reason_code"] == "window_expired" and result["route"] is None


def test_regret_route_and_policy_sections(data):
    result = check(data, 7, "regret", date(2026, 2, 19))
    assert result["route"] == "return_refund"
    assert result["policy_sections"] == ["4.1", "4.4"]
    assert "return_request" in result["next_step"]
    assert result["conditions"] and result["ask_customer"]


def test_preference_route_depends_on_stock(data):
    result = check(data, 7, "preference", date(2026, 2, 19))
    assert result["route"] == "exchange" and result["policy_sections"] == ["4.3", "4.4"]
    assert any("stock" in c for c in result["conditions"])


@pytest.mark.parametrize(
    ("today", "eligible", "route", "sections"),
    [
        (date(2026, 3, 5), True, "exchange", ["4.2"]),
        (date(2026, 3, 6), True, "legal_warranty", ["4.2", "8.1"]),
        (date(2026, 3, 25), True, "legal_warranty", ["4.2", "8.1"]),
        (date(2026, 5, 18), True, "legal_warranty", ["4.2", "8.1"]),
        (date(2026, 5, 19), False, "manufacturer_warranty", ["8.2"]),
        (date(2026, 6, 1), False, "manufacturer_warranty", ["8.2"]),
    ],
)
def test_defect_routes_follow_purchase_then_receipt_windows(data, today, eligible, route, sections):
    result = check(data, 7, "defect", today)
    assert (result["eligible"], result["route"]) == (eligible, route)
    assert result["policy_sections"] == sections
    assert result["days_since_purchase"] == (today - date(2026, 2, 3)).days


def test_defect_deadlines(data):
    exchange = check(data, 7, "defect", date(2026, 3, 5))
    assert exchange["deadline"] == "2026-03-05"
    legal = check(data, 7, "defect", date(2026, 3, 25))
    assert legal["deadline"] == "2026-05-18"
    expired = check(data, 7, "defect", date(2026, 6, 1))
    assert expired["deadline"] is None and expired["reason_code"] == "window_expired"
    assert "defect" in exchange["next_step"]


def test_verification_and_ownership_are_required(data):
    unverified = check_return_eligibility(data, SessionState(), 7, "regret", date(2026, 2, 19))
    assert unverified["error"]["code"] == "not_verified"
    foreign = check(data, 7, "regret", date(2026, 2, 19), customer=2)
    assert foreign["error"]["code"] == "order_not_found"


@pytest.mark.parametrize("reason", ["other", "", None])
def test_reason_must_be_known(data, reason):
    result = check(data, 7, reason, date(2026, 2, 19))
    assert is_error(result) and result["error"]["code"] == "invalid_argument"


def test_every_verdict_has_the_same_keys(data):
    keys = {
        "order_id",
        "reason",
        "eligible",
        "reason_code",
        "route",
        "received_on",
        "days_since_receipt",
        "days_since_purchase",
        "deadline",
        "conditions",
        "ask_customer",
        "policy_sections",
        "next_step",
    }
    for order, customer in ((7, 14), (17, 15), (8, 2)):
        assert set(check(data, order, "defect", date(2026, 3, 25), customer)) == keys
