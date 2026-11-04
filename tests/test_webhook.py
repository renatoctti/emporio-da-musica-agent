"""Spec 24: the optional webhook that tells the store team about a new ticket."""

import json
import threading
import urllib.error
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from emporio import handoff
from emporio.config import ConfigError, load_settings
from emporio.db import HandoffStore, connect
from emporio.evals import runner
from emporio.orders import verify_customer
from emporio.session import SessionState
from emporio.webhook import handoff_body, make_notifier
from tests.test_web import DATA

NOW = datetime(2026, 3, 25, 10, 0)
EMAIL = "anacarol.ferreira@coldmail.com"


def new_ticket(store=None, **over):
    store = store or HandoffStore(connect(":memory:"))
    return store.create(
        **{
            "category": "complaint",
            "summary": "Violão chegou riscado.",
            "customer_id": 2,
            "order_id": 8,
            "session_id": None,
            "created_at": NOW,
            "due_at": datetime(2026, 3, 26, 10, 0),
            **over,
        }
    )


# --- RF-01 -------------------------------------------------------------------------------------


def test_the_address_is_optional_and_must_be_http_or_https():
    base = {"EMPORIO_DB_PATH": ":memory:"}
    assert load_settings(base).handoff_webhook_url is None
    assert load_settings({**base, "HANDOFF_WEBHOOK_URL": "  "}).handoff_webhook_url is None
    url = "http://localhost:5678/webhook/handoff"
    assert load_settings({**base, "HANDOFF_WEBHOOK_URL": url}).handoff_webhook_url == url
    for bad in ("ftp://x/y", "file:///etc/passwd", "localhost:5678", "http://"):
        with pytest.raises(ConfigError):
            load_settings({**base, "HANDOFF_WEBHOOK_URL": bad})


def test_no_address_means_no_notifier():
    assert make_notifier(None) is None


# --- RF-02, RF-03 ------------------------------------------------------------------------------


class _Receiver(BaseHTTPRequestHandler):
    def do_POST(self):
        size = int(self.headers.get("Content-Length", 0))
        self.server.received.append(
            (self.headers.get("Content-Type"), json.loads(self.rfile.read(size)))
        )
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


def test_a_new_ticket_is_posted_as_json_to_a_real_local_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Receiver)
    server.received = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        notify = make_notifier(f"http://127.0.0.1:{server.server_port}/hook")
        notify(new_ticket(session_id=None))
    finally:
        server.shutdown()
        server.server_close()
    ((content_type, body),) = server.received
    assert content_type == "application/json"
    assert body["event"] == "handoff.created" and body["category"] == "complaint"
    assert body["protocol"].startswith("EMP-20260325-") and body["order_id"] == 8
    assert body["summary"] == "Violão chegou riscado."
    assert body["created_at"] == "2026-03-25T10:00:00" and body["due_at"] == "2026-03-26T10:00:00"
    assert body["protocol"] in body["text"] and "Reclamação" in body["text"]


def test_the_message_has_no_customer_data():
    body = handoff_body(new_ticket())
    assert set(body) == {
        "event",
        "text",
        "protocol",
        "category",
        "summary",
        "order_id",
        "session_id",
        "created_at",
        "due_at",
    }
    assert "customer" not in json.dumps(body).lower() and EMAIL not in json.dumps(body)


# --- RF-04 -------------------------------------------------------------------------------------


def _open(store, state, notify, **over):
    args = {
        "category": "complaint",
        "summary": "Atraso.",
        "order_id": 8,
        "session_id": None,
        "now": NOW,
        "notify": notify,
        **over,
    }
    return handoff.open_handoff(DATA, state, store, **args)


def test_only_a_new_ticket_notifies_not_a_duplicate():
    store, state, sent = HandoffStore(connect(":memory:")), SessionState(), []
    assert verify_customer(DATA, state, 8, EMAIL)["verified"] is True
    first = _open(store, state, sent.append)
    second = _open(store, state, sent.append)
    assert first["duplicate"] is False and second["duplicate"] is True
    assert [t.protocol for t in sent] == [first["protocol"]]


def test_a_failed_validation_notifies_nothing():
    sent = []
    result = _open(HandoffStore(connect(":memory:")), SessionState(), sent.append, category="x")
    assert "error" in result and sent == []


# --- RF-05 -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError("slow"),
        ConnectionRefusedError("down"),
        urllib.error.URLError("no route"),
        urllib.error.HTTPError("http://x", 500, "boom", {}, None),
        ValueError("bad url"),
    ],
)
def test_a_webhook_failure_is_ignored_and_the_tool_still_answers(failure):
    def opener(request, timeout):
        raise failure

    notify = make_notifier("http://127.0.0.1:9/hook", opener=opener)
    store, state = HandoffStore(connect(":memory:")), SessionState()
    verify_customer(DATA, state, 8, EMAIL)
    result = _open(store, state, notify)
    assert result["protocol"].startswith("EMP-") and len(store.list_open()) == 1


def test_the_request_has_a_short_timeout():
    seen = {}

    def opener(request, timeout):
        seen["timeout"], seen["url"] = timeout, request.full_url

        class Done:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        return Done()

    make_notifier("https://hooks.example/abc", opener=opener)(new_ticket())
    assert seen == {"timeout": 3.0, "url": "https://hooks.example/abc"}


# --- RF-07 -------------------------------------------------------------------------------------


def test_the_evaluation_runner_does_not_know_the_webhook():
    source = runner.__loader__.get_source(runner.__name__)
    assert "webhook" not in source.lower()
