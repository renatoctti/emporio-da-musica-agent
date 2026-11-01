from datetime import date
from pathlib import Path

import pytest

from emporio.data import load_store_data
from emporio.orders import (
    STATUS_MEANING,
    get_order_status,
    list_my_orders,
    verify_customer,
)
from emporio.results import is_error
from emporio.session import MAX_FAILED_VERIFICATIONS, SessionState

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TODAY = date(2026, 3, 25)
ANA_EMAIL = "anacarol.ferreira@coldmail.com"  # customer 2, owner of order 8


@pytest.fixture(scope="module")
def data():
    return load_store_data(DATA_DIR)


def verified(customer_id):
    return SessionState(verified_customer_id=customer_id)


def test_a_new_session_is_unverified():
    state = SessionState()
    assert state.verified_customer_id is None and state.failed_verifications == 0
    assert MAX_FAILED_VERIFICATIONS == 3


@pytest.mark.parametrize(
    "contact",
    [
        ANA_EMAIL,
        "  ANACAROL.Ferreira@Coldmail.com ",
        "(67) 99654-7821",
        "+55 67 99654 7821",
        "67996547821",
    ],
)
def test_verification_accepts_email_and_phone_formats(data, contact):
    state = SessionState()
    result = verify_customer(data, state, 8, contact)
    assert result == {"verified": True, "customer_first_name": "Ana"}
    assert state.verified_customer_id == 2


def test_failures_look_identical_whether_or_not_the_order_exists(data):
    wrong_contact, unknown_order = SessionState(), SessionState()
    a = verify_customer(data, wrong_contact, 8, "errado@exemplo.com")
    b = verify_customer(data, unknown_order, 9999, ANA_EMAIL)
    assert a == b == {"verified": False, "attempts_left": 2}
    assert wrong_contact.verified_customer_id is None


def test_three_failures_lock_the_session_even_for_the_right_contact(data):
    state = SessionState()
    attempts = [verify_customer(data, state, 8, "x@y.com")["attempts_left"] for _ in range(3)]
    assert attempts == [2, 1, 0]
    locked = verify_customer(data, state, 8, ANA_EMAIL)
    assert is_error(locked) and locked["error"]["code"] == "verification_locked"
    assert state.verified_customer_id is None


def test_a_success_resets_the_failure_counter(data):
    state = SessionState()
    verify_customer(data, state, 8, "x@y.com")
    verify_customer(data, state, 8, ANA_EMAIL)
    assert state.failed_verifications == 0


def test_shared_email_verifies_the_owner_of_the_order_only(data):
    state = SessionState()
    assert verify_customer(data, state, 10, "bruno.martins@jmail.com")["verified"] is True
    assert state.verified_customer_id == 11
    assert [o["order_id"] for o in list_my_orders(data, state)["orders"]] == [10]
    other = SessionState()
    assert verify_customer(data, other, 10, "(67) 99456-3456")["verified"] is False  # customer 43


def test_phone_without_area_code_does_not_verify(data):
    state = SessionState()
    assert verify_customer(data, state, 8, "99654-7821")["verified"] is False
    assert state.failed_verifications == 1


@pytest.mark.parametrize(("order_id", "contact"), [(8, ""), (8, "   "), ("abc", ANA_EMAIL)])
def test_bad_input_is_invalid_argument_and_not_counted(data, order_id, contact):
    state = SessionState()
    result = verify_customer(data, state, order_id, contact)
    assert is_error(result) and result["error"]["code"] == "invalid_argument"
    assert state.failed_verifications == 0


def test_order_status_requires_verification(data):
    result = get_order_status(data, SessionState(), 8, TODAY)
    assert is_error(result) and result["error"]["code"] == "not_verified"


def test_other_customers_orders_look_like_missing_orders(data):
    state = verified(2)
    other = get_order_status(data, state, 10, TODAY)
    missing = get_order_status(data, state, 9999, TODAY)
    assert other["error"]["code"] == "order_not_found"
    assert other == missing


def test_order_status_content(data):
    shipped = get_order_status(data, verified(2), 8, TODAY)
    assert shipped["status"] == "shipped"
    assert shipped["status_meaning"] == STATUS_MEANING["shipped"]
    assert shipped["tracking_code"] == "BRJL5544332BR"
    assert shipped["estimated_delivery"] == "2026-02-28"
    assert shipped["order_date"] == "2026-02-15"
    assert shipped["payment"] == {"method": "debit", "installments": None}

    mismatch = get_order_status(data, verified(12), 3, TODAY)
    assert mismatch["total_brl"] == 3450.0  # recorded total, not the item sum (3498)
    assert mismatch["items"] == [
        {"product_id": 130, "name": "Kala KA-ABP-CTG Barítono Cedar", "quantity": 2}
    ]
    assert mismatch["payment"] == {"method": "credit", "installments": 12}


def test_cancelled_order_carries_its_reason(data):
    result = get_order_status(data, verified(15), 17, TODAY)
    assert result["status"] == "cancelled"
    assert result["notes"] == "Pedido cancelado pelo cliente antes do processamento"
    assert result["tracking_code"] is None and result["estimated_delivery"] is None


def test_every_status_has_a_meaning(data):
    assert set(data.orders.status) <= set(STATUS_MEANING)


@pytest.mark.parametrize(
    ("customer", "order", "today", "expected"),
    [
        (2, 8, date(2026, 3, 25), True),
        (2, 8, date(2026, 2, 20), False),
        (2, 8, date(2026, 2, 28), False),
        (3, 1, TODAY, None),
        (16, 12, TODAY, None),
    ],
)
def test_estimated_delivery_passed_flag(data, customer, order, today, expected):
    result = get_order_status(data, verified(customer), order, today)
    assert result["estimated_delivery_passed"] is expected


def test_list_my_orders_is_newest_first(data):
    result = list_my_orders(data, verified(3))
    assert [o["order_id"] for o in result["orders"]] == [19, 1]
    first = result["orders"][0]
    assert first == {
        "order_id": 19,
        "order_date": "2026-02-22",
        "status": "cancelled",
        "total_brl": 7499.0,
        "item_count": 1,
    }


def test_list_my_orders_requires_verification(data):
    result = list_my_orders(data, SessionState())
    assert is_error(result) and result["error"]["code"] == "not_verified"
