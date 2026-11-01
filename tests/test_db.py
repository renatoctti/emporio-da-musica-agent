import sqlite3
from datetime import date, datetime, timedelta

import pytest

from emporio.db import (
    HANDOFF_CATEGORIES,
    HandoffStore,
    SessionStore,
    UnknownSessionError,
    connect,
)

NOW = datetime(2026, 3, 25, 10, 0)
DUE = datetime(2026, 3, 27, 16, 0)


@pytest.fixture
def conn():
    connection = connect(":memory:")
    yield connection
    connection.close()


def make_handoff(store, session_id=None, **overrides):
    args = {
        "category": "complaint",
        "summary": "Violão chegou riscado.",
        "customer_id": 3,
        "order_id": 1,
        "session_id": session_id,
        "created_at": NOW,
        "due_at": DUE,
    }
    args.update(overrides)
    return store.create(**args)


def test_connect_creates_schema_directory_and_foreign_keys(tmp_path):
    path = tmp_path / "var" / "emporio.db"
    conn = connect(path)
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"sessions", "messages", "handoffs"} <= tables
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()


def test_data_survives_reconnecting_to_the_same_file(tmp_path):
    path = tmp_path / "emporio.db"
    first = connect(path)
    sid = SessionStore(first).create_session("m", None, NOW)
    make_handoff(HandoffStore(first), sid)
    first.close()

    second = connect(path)
    assert [s.id for s in SessionStore(second).list_sessions()] == [sid]
    assert len(HandoffStore(second).list_open()) == 1
    second.close()


def test_session_ids_are_unique_short_hex(conn):
    store = SessionStore(conn)
    ids = {store.create_session("m", date(2026, 3, 25), NOW) for _ in range(100)}
    assert len(ids) == 100
    assert all(len(i) == 8 and int(i, 16) >= 0 and i == i.lower() for i in ids)


def test_messages_round_trip_in_order_with_tool_calls_and_unicode(conn):
    store = SessionStore(conn)
    sid = store.create_session("m", None, NOW)
    messages = [
        {"role": "user", "content": "Oi! Quanto custa o Takamine GD20? 🎸"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "get_product", "arguments": '{"product_id": 95}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": '{"price_brl": 2199.0}'},
        {"role": "assistant", "content": "Custa R$ 2.199,00 — ótimo violão."},
    ]
    for m in messages:
        store.append_message(sid, m, NOW)
    assert store.load_messages(sid) == messages


def test_load_preserves_order_for_many_messages(conn):
    store = SessionStore(conn)
    sid = store.create_session("m", None, NOW)
    for i in range(10):
        store.append_message(sid, {"role": "user", "content": str(i)}, NOW)
    assert [m["content"] for m in store.load_messages(sid)] == [str(i) for i in range(10)]


def test_session_without_messages_loads_empty(conn):
    store = SessionStore(conn)
    assert store.load_messages(store.create_session("m", None, NOW)) == []


def test_unknown_session_raises(conn):
    store = SessionStore(conn)
    with pytest.raises(UnknownSessionError):
        store.append_message("nope", {"role": "user", "content": "x"}, NOW)
    with pytest.raises(UnknownSessionError):
        store.load_messages("nope")


def test_list_sessions_is_newest_first_with_counts_and_first_user_message(conn):
    store = SessionStore(conn)
    old = store.create_session("m1", None, NOW)
    mid = store.create_session("m2", None, NOW + timedelta(hours=1))
    new = store.create_session("m3", None, NOW + timedelta(hours=2))
    store.append_message(old, {"role": "user", "content": "primeira pergunta"}, NOW)
    store.append_message(old, {"role": "assistant", "content": "resposta"}, NOW)
    store.append_message(mid, {"role": "assistant", "content": "sem usuário"}, NOW)

    listed = store.list_sessions()
    assert [s.id for s in listed] == [new, mid, old]
    by_id = {s.id: s for s in listed}
    assert (by_id[old].message_count, by_id[old].first_user_message) == (2, "primeira pergunta")
    assert (by_id[mid].message_count, by_id[mid].first_user_message) == (1, None)
    assert by_id[new].message_count == 0 and by_id[new].model == "m3"
    assert by_id[old].created_at == NOW
    assert len(store.list_sessions(limit=2)) == 2


def test_handoff_protocol_and_fields(conn):
    sid = SessionStore(conn).create_session("m", None, NOW)
    store = HandoffStore(conn)
    first = make_handoff(store, sid)
    second = make_handoff(store, sid, category="defect", order_id=2)
    assert first.protocol == "EMP-20260325-0001"
    assert second.protocol == "EMP-20260325-0002"
    assert (first.category, first.status, first.customer_id, first.order_id) == (
        "complaint",
        "open",
        3,
        1,
    )
    assert first.created_at == NOW and first.due_at == DUE and first.session_id == sid


def test_handoff_accepts_missing_customer_order_and_session(conn):
    h = make_handoff(HandoffStore(conn), customer_id=None, order_id=None, session_id=None)
    assert (h.customer_id, h.order_id, h.session_id) == (None, None, None)


def test_invalid_category_stores_nothing(conn):
    store = HandoffStore(conn)
    with pytest.raises(ValueError, match="category"):
        make_handoff(store, category="refund")
    assert conn.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0
    assert HANDOFF_CATEGORIES == ("complaint", "return_request", "defect", "other")


def test_unknown_session_foreign_key_is_enforced_and_rolled_back(conn):
    store = HandoffStore(conn)
    with pytest.raises(sqlite3.IntegrityError):
        make_handoff(store, session_id="ghost")
    assert conn.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0] == 0


def test_list_open_and_find_open(conn):
    store = HandoffStore(conn)
    a = make_handoff(store, order_id=1, category="complaint")
    b = make_handoff(store, order_id=2, category="return_request")
    c = make_handoff(store, order_id=3, category="defect")
    with conn:
        conn.execute("UPDATE handoffs SET status = 'closed' WHERE id = ?", (c.id,))
    assert [h.id for h in store.list_open()] == [a.id, b.id]
    assert store.find_open(2, "return_request").id == b.id
    assert store.find_open(2, "complaint") is None
    assert store.find_open(3, "defect") is None


def test_append_messages_stores_a_whole_turn_in_order(conn):
    store = SessionStore(conn)
    sid = store.create_session("m", None, NOW)
    turn = [{"role": "user", "content": "oi"}, {"role": "assistant", "content": "olá"}]
    store.append_messages(sid, turn, NOW)
    store.append_messages(sid, [{"role": "user", "content": "de novo"}], NOW)
    assert store.load_messages(sid) == [*turn, {"role": "user", "content": "de novo"}]
    with pytest.raises(UnknownSessionError):
        store.append_messages("nope", turn, NOW)


def test_append_messages_is_all_or_nothing(conn):
    store = SessionStore(conn)
    sid = store.create_session("m", None, NOW)
    with pytest.raises(TypeError):
        store.append_messages(sid, [{"role": "user", "content": "ok"}, {"bad": object()}], NOW)
    assert store.load_messages(sid) == []


def test_get_session_returns_the_metadata(conn):
    store = SessionStore(conn)
    sid = store.create_session("some/model", date(2026, 3, 25), NOW)
    store.append_message(sid, {"role": "user", "content": "primeira"}, NOW)
    info = store.get_session(sid)
    assert (info.id, info.model, info.reference_date) == (sid, "some/model", date(2026, 3, 25))
    assert (info.message_count, info.first_user_message, info.created_at) == (1, "primeira", NOW)
    assert store.get_session(store.create_session("m", None, NOW)).reference_date is None
    with pytest.raises(UnknownSessionError):
        store.get_session("nope")
    assert store.list_sessions()[0].reference_date is None
