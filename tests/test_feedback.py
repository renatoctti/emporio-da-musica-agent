"""Spec 23: thumbs up and down on the answers."""

import json
from datetime import datetime

import pytest

from emporio import cli
from emporio.db import SessionStore, UnknownSessionError, connect
from emporio.web.app import STATIC_DIR
from tests.fakes import assistant_text
from tests.test_web import body, chat, get, make_app, post

NOW = datetime(2026, 3, 25, 10, 0)


def feedback(app, **payload):
    return post(app, "/api/feedback", payload)


def two_turn_app():
    return make_app([assistant_text("Primeira."), assistant_text("Segunda.")])[0]


# --- RF-01 -------------------------------------------------------------------------------------


def test_a_rating_is_replaced_by_the_next_one_and_removed_with_none():
    store = SessionStore(connect(":memory:"))
    session = store.create_session("m", None, NOW)
    store.save_feedback(session, 0, "up", None, NOW)
    store.save_feedback(session, 1, "down", "errou o prazo", NOW)
    assert store.load_feedback(session) == {0: ("up", None), 1: ("down", "errou o prazo")}
    store.save_feedback(session, 0, "down", None, NOW)
    store.save_feedback(session, 1, None, None, NOW)
    assert store.load_feedback(session) == {0: ("down", None)}
    with pytest.raises(UnknownSessionError):
        store.save_feedback("nope", 0, "up", None, NOW)


# --- RF-02, RF-03, RF-06 -----------------------------------------------------------------------


def test_a_rating_is_saved_and_comes_back_in_the_state_after_a_reload():
    app = two_turn_app()
    chat(app, "um")
    chat(app, "dois")
    assert feedback(app, turn_index=1, rating="down", comment="  muito curta ").status == 200
    assert feedback(app, turn_index=0, rating="up").status == 200
    turns = body(get(app, "/api/state"))["turns"]
    assert [t["feedback"] for t in turns] == ["up", "down"]
    assert app.sessions.load_feedback(app.session_id)[1] == ("down", "muito curta")
    assert feedback(app, turn_index=0, rating=None).status == 200
    assert [t["feedback"] for t in body(get(app, "/api/state"))["turns"]] == [None, "down"]


@pytest.mark.parametrize(
    "payload",
    [
        {"turn_index": 0},  # no rating key
        {"turn_index": 0, "rating": "meh"},
        {"turn_index": "0", "rating": "up"},
        {"turn_index": True, "rating": "up"},
        {"turn_index": -1, "rating": "up"},
        {"turn_index": 5, "rating": "up"},  # there is only one turn
        {"turn_index": 0, "rating": "up", "comment": 7},
        {"turn_index": 0, "rating": "up", "comment": "x" * 501},
    ],
)
def test_a_bad_rating_is_a_400_and_stores_nothing(payload):
    app = make_app([assistant_text("Oi.")])[0]
    chat(app, "oi")
    assert feedback(app, **payload).status == 400
    assert app.sessions.load_feedback(app.session_id) == {}


def test_the_route_is_post_only_and_a_reset_starts_clean():
    app = make_app([assistant_text("Oi.")])[0]
    assert get(app, "/api/feedback").status == 405
    chat(app, "oi")
    feedback(app, turn_index=0, rating="up")
    old = app.session_id
    post(app, "/api/reset", {})
    assert body(get(app, "/api/state"))["turns"] == []
    assert app.sessions.load_feedback(old) == {0: ("up", None)}


# --- RF-04 -------------------------------------------------------------------------------------


def test_each_answer_has_two_rating_buttons():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    sheet = (STATIC_DIR / "app.css").read_text(encoding="utf-8")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for part in ("/api/feedback", "aria-pressed", "Resposta boa", "Resposta ruim", "rateButton"):
        assert part in script, part
    assert 'id="i-up"' in html and 'id="i-down"' in html
    assert ".rate-btn" in sheet


# --- RF-05 -------------------------------------------------------------------------------------


def _run(argv, env):
    written: list[str] = []
    code = cli.main(argv, env=env, client_factory=lambda s: None, read=input, write=written.append)
    return code, "\n".join(written)


def test_the_command_lists_the_bad_answers_and_exports_candidates(tmp_path):
    db = tmp_path / "e.db"
    env = {"EMPORIO_DB_PATH": str(db), "EMPORIO_TODAY": "2026-03-25"}
    assert _run(["feedback"], env) == (0, "No answers rated down yet.")
    store = SessionStore(connect(db))
    session = store.create_session("m", None, NOW)
    store.append_messages(
        session,
        [
            {"role": "user", "content": "Qual o prazo?"},
            {"role": "assistant", "content": "10 dias."},
        ],
        NOW,
    )
    store.append_messages(
        session,
        [{"role": "user", "content": "E o frete?"}, {"role": "assistant", "content": "Grátis."}],
        NOW,
    )
    store.save_feedback(session, 0, "down", "prazo errado", NOW)
    store.save_feedback(session, 1, "up", None, NOW)
    code, out = _run(["feedback"], env)
    assert (
        code == 0 and "Qual o prazo?" in out and "prazo errado" in out and "E o frete?" not in out
    )
    target = tmp_path / "candidates.json"
    assert _run(["feedback", "-o", str(target)], env)[0] == 0
    assert json.loads(target.read_text(encoding="utf-8")) == [
        {
            "session_id": session,
            "turn_index": 0,
            "question": "Qual o prazo?",
            "reply": "10 dias.",
            "comment": "prazo errado",
        }
    ]
