from datetime import date, datetime
from pathlib import Path

import pytest

from emporio.data import load_store_data
from emporio.db import HandoffStore, SessionStore, connect
from emporio.handoff import MAX_SUMMARY_CHARS, RESPONSE_BUSINESS_HOURS, open_handoff
from emporio.results import is_error
from emporio.session import SessionState

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
MONDAY_10 = datetime(2026, 3, 23, 10, 0)


@pytest.fixture(scope="module")
def data():
    return load_store_data(DATA_DIR)


@pytest.fixture
def conn():
    connection = connect(":memory:")
    yield connection
    connection.close()


def call(data, conn, state=None, **overrides):
    args = {
        "category": "return_request",
        "summary": "Customer wants to return the ukulele (regret, within 7 days).",
        "order_id": 7,
        "session_id": None,
        "now": MONDAY_10,
    }
    args.update(overrides)
    state = state or SessionState(verified_customer_id=14)
    return open_handoff(data, state, HandoffStore(conn), **args)


def stored(conn):
    return HandoffStore(conn).list_open()


def test_constants():
    assert (MAX_SUMMARY_CHARS, RESPONSE_BUSINESS_HOURS) == (600, 24)


def test_creates_a_ticket_with_protocol_and_business_hours_deadline(data, conn):
    sessions = SessionStore(conn)
    sid = sessions.create_session("m", date(2026, 3, 23), MONDAY_10)
    result = call(data, conn, session_id=sid)
    assert result == {
        "protocol": "EMP-20260323-0001",
        "category": "return_request",
        "status": "open",
        "due_at": "2026-03-25T16:00:00",
        "store_open_now": True,
        "duplicate": False,
    }
    ticket = stored(conn)[0]
    assert (ticket.customer_id, ticket.order_id, ticket.session_id) == (14, 7, sid)
    assert ticket.summary.startswith("Customer wants to return")


def test_out_of_hours_ticket_counts_from_the_next_opening(data, conn):
    sunday = datetime(2026, 3, 29, 15, 0)
    result = call(data, conn, now=sunday)
    assert result["store_open_now"] is False
    assert result["due_at"] == "2026-04-01T15:00:00"


@pytest.mark.parametrize(
    "overrides",
    [
        {"category": "refund"},
        {"summary": ""},
        {"summary": "   "},
        {"summary": "a" * (MAX_SUMMARY_CHARS + 1)},
    ],
)
def test_invalid_arguments_store_nothing(data, conn, overrides):
    result = call(data, conn, **overrides)
    assert is_error(result) and result["error"]["code"] == "invalid_argument"
    assert stored(conn) == []


def test_summary_at_the_limit_is_accepted(data, conn):
    assert "protocol" in call(data, conn, summary="a" * MAX_SUMMARY_CHARS)


def test_an_order_requires_verification_and_ownership(data, conn):
    unverified = call(data, conn, state=SessionState())
    assert unverified["error"]["code"] == "not_verified"
    foreign = call(data, conn, order_id=8)  # customer 14 does not own order 8
    assert foreign["error"]["code"] == "order_not_found"
    assert stored(conn) == []


def test_an_unverified_customer_can_register_a_complaint_without_an_order(data, conn):
    result = call(data, conn, state=SessionState(), category="complaint", order_id=None)
    assert result["protocol"].startswith("EMP-")
    ticket = stored(conn)[0]
    assert ticket.customer_id is None and ticket.order_id is None


def test_a_verified_customer_without_an_order_is_linked_to_the_ticket(data, conn):
    call(data, conn, category="other", order_id=None)
    ticket = stored(conn)[0]
    assert ticket.customer_id == 14 and ticket.order_id is None


def test_an_open_ticket_for_the_same_order_and_category_is_reused(data, conn):
    first = call(data, conn)
    second = call(data, conn, summary="Same request again.", now=datetime(2026, 3, 24, 11, 0))
    assert second["duplicate"] is True
    assert second["protocol"] == first["protocol"] and second["due_at"] == first["due_at"]
    assert len(stored(conn)) == 1
    other_category = call(data, conn, category="defect")
    assert other_category["duplicate"] is False and len(stored(conn)) == 2
