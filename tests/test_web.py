import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from emporio.config import load_settings
from emporio.data import load_store_data
from emporio.orders import verify_customer
from emporio.policies import load_policy_sections
from emporio.session import SessionState
from emporio.web.app import STATIC_DIR, WebApp, trace_item
from emporio.web.server import make_server
from tests.fakes import FakeChatClient, assistant_calls, assistant_text, tool_call

ROOT = Path(__file__).resolve().parents[1]
DATA = load_store_data(ROOT / "data")
POLICIES = load_policy_sections(ROOT / "data" / "políticas_da_loja.pdf")
HOST = "127.0.0.1:8765"
JSON_HEADERS = {"Host": HOST, "Content-Type": "application/json"}


def make_app(script=(), *, today="2026-03-25", client=None):
    env = {"EMPORIO_DB_PATH": ":memory:", "LLM_MODEL": "test/model"}
    if today:
        env["EMPORIO_TODAY"] = today
    client = client or FakeChatClient(list(script))
    app = WebApp(load_settings(env), client, port=8765, data=DATA, policies=POLICIES)
    return app, client


def get(app, path, headers=None):
    return app.handle("GET", path, headers or {"Host": HOST}, b"")


def post(app, path, payload, headers=None):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return app.handle("POST", path, headers or JSON_HEADERS, body)


def body(response):
    return json.loads(response.body)


def chat(app, text):
    response = post(app, "/api/chat", {"text": text})
    assert response.status == 200, response.body
    return body(response)


# --- pages and static files -------------------------------------------------------------------


def test_the_page_and_the_static_files_are_served_with_the_right_types():
    app, _ = make_app()
    page = get(app, "/")
    assert page.status == 200 and page.content_type == "text/html; charset=utf-8"
    assert b'lang="pt-BR"' in page.body and "<title>Melô".encode() in page.body
    assert dict(page.headers)["Content-Security-Policy"].startswith("default-src 'self'")
    for path, kind in (
        ("/static/app.css", "text/css; charset=utf-8"),
        ("/static/app.js", "text/javascript; charset=utf-8"),
        ("/static/theme.js", "text/javascript; charset=utf-8"),
        ("/static/favicon.svg", "image/svg+xml"),
    ):
        response = get(app, path)
        assert (response.status, response.content_type) == (200, kind), path


@pytest.mark.parametrize(
    "path",
    [
        "/static/../../pyproject.toml",
        "/static/..%2f..%2fpyproject.toml",
        "/static/%2e%2e/app.py",
        "/static/nope.css",
        "/static/",
        "/static/sub/app.css",
        "/api/nope",
        "/nope",
    ],
)
def test_anything_outside_the_static_folder_is_404(path):
    app, _ = make_app()
    assert get(app, path).status == 404


def test_static_files_make_no_external_request_and_never_use_inner_html():
    assert {p.name for p in STATIC_DIR.iterdir()} >= {
        "index.html",
        "app.css",
        "app.js",
        "theme.js",
        "favicon.svg",
    }
    import re

    external = re.compile(r"""(?:src|href)\s*=\s*["']https?:|url\(\s*["']?https?:|@import""")
    for path in STATIC_DIR.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not external.search(text), path.name
        assert "innerHTML" not in text and "insertAdjacentHTML" not in text, path.name
    assert 'lang="pt-BR"' in (STATIC_DIR / "index.html").read_text(encoding="utf-8")


# --- state ------------------------------------------------------------------------------------


def test_state_on_a_weekday_morning():
    app, _ = make_app()
    state = body(get(app, "/api/state"))
    store = state["store"]
    assert store["open"] is True and "fecha às 18:00" in store["status_text"]
    assert [h["label"] for h in store["hours"]] == [
        "Segunda a sexta",
        "Sábado",
        "Domingo e feriados",
    ]
    assert (
        store["hours"][0]["value"] == "09:00 às 18:00" and store["hours"][2]["value"] == "Fechado"
    )
    assert store["phone"] == "(67) 3341-4444" and "14 de Maio" in store["address"]
    assert state["reference"] == {"date": "2026-03-25", "label": "25/03/2026", "simulated": True}
    assert state["model"] == "test/model" and len(state["session_id"]) == 8
    assert state["verified"] is None and state["handoffs_open"] == 0 and state["turns"] == []
    assert len(state["suggestions"]) == 4
    assert all({"topic", "label", "text"} <= set(s) for s in state["suggestions"])


def test_state_when_the_store_is_closed_on_sunday():
    app, _ = make_app(today="2026-03-29")
    store = body(get(app, "/api/state"))["store"]
    assert store["open"] is False
    assert store["status_text"] == "Fechada agora · abre segunda-feira às 09:00"
    assert store["next_opening"] == "2026-03-30T09:00:00"


def test_state_with_the_real_clock_is_not_simulated():
    app, _ = make_app(today=None)
    assert body(get(app, "/api/state"))["reference"]["simulated"] is False


def test_the_test_customers_really_pass_the_identity_check():
    app, _ = make_app()
    customers = body(get(app, "/api/state"))["test_customers"]
    assert len(customers) == 2
    for customer in customers:
        result = verify_customer(DATA, SessionState(), customer["order_id"], customer["email"])
        assert result["verified"] is True, customer
        assert customer["note"]


# --- chat -------------------------------------------------------------------------------------


def test_a_plain_turn_is_stored_and_returned():
    app, client = make_app([assistant_text("Oi! Como posso ajudar?")])
    result = chat(app, "  Oi  ")
    assert result["reply"] == "Oi! Como posso ajudar?"
    assert result["trace"] == [] and result["verified"] is None and result["handoffs_open"] == 0
    stored = app.sessions.load_messages(app.session_id)
    assert [m["role"] for m in stored] == ["user", "assistant"]
    assert stored[0]["content"] == "Oi"
    assert client.calls[0][0][0]["role"] == "system"


def test_a_tool_turn_returns_the_trace_and_the_state_rebuilds_it_after_a_reload():
    script = [
        assistant_calls(tool_call("c1", "get_product", {"product_id": 95})),
        assistant_text("O Takamine GD20 custa R$ 2.199,00."),
    ]
    app, _ = make_app(script)
    result = chat(app, "Quanto custa o Takamine GD20?")
    item = result["trace"][0]
    assert (item["name"], item["kind"], item["ok"]) == ("get_product", "data", True)
    assert item["arguments"] == {"product_id": 95} and item["result"]["found"] is True
    assert "Takamine GD20" in item["summary"]
    turns = body(get(app, "/api/state"))["turns"]
    assert turns == [
        {
            "user": "Quanto custa o Takamine GD20?",
            "reply": result["reply"],
            "trace": result["trace"],
        }
    ]


def test_several_tool_calls_in_one_turn_keep_their_order():
    script = [
        assistant_calls(
            tool_call("c1", "search_products", {"query": "ohana"}),
            tool_call("c2", "get_policy_sections", {"section_ids": ["3.1"]}),
        ),
        assistant_text("Pronto."),
    ]
    app, _ = make_app(script)
    trace = chat(app, "Ohana em 10x?")["trace"]
    assert [(t["name"], t["kind"]) for t in trace] == [
        ("search_products", "data"),
        ("get_policy_sections", "policy"),
    ]


def test_verification_shows_up_and_a_reset_clears_it():
    script = [
        assistant_calls(
            tool_call(
                "c1",
                "verify_customer",
                {"order_id": 8, "contact": "anacarol.ferreira@coldmail.com"},
            )
        ),
        assistant_text("Confirmei, Ana."),
    ]
    app, _ = make_app(script)
    first_session = app.session_id
    result = chat(app, "Pedido 8, meu e-mail é anacarol.ferreira@coldmail.com")
    assert result["verified"] == {"first_name": "Ana"}
    assert body(get(app, "/api/state"))["verified"] == {"first_name": "Ana"}
    assert result["trace"][0]["arguments"]["contact"] == "(oculto)"

    reset = body(post(app, "/api/reset", {}))
    assert reset["session_id"] != first_session and reset["verified"] is None
    state = body(get(app, "/api/state"))
    assert state["verified"] is None and state["turns"] == []
    assert app.sessions.load_messages(first_session)  # the old conversation stays stored


def test_a_handoff_opened_in_a_chat_is_listed_for_the_store():
    script = [
        assistant_calls(
            tool_call("c1", "open_handoff", {"category": "complaint", "summary": "Violão riscado."})
        ),
        assistant_text("Registrei o chamado."),
    ]
    app, _ = make_app(script)
    assert body(get(app, "/api/handoffs"))["tickets"] == []
    result = chat(app, "O violão chegou riscado, quero reclamar.")
    assert result["handoffs_open"] == 1 and result["trace"][0]["kind"] == "handoff"
    tickets = body(get(app, "/api/handoffs"))["tickets"]
    assert len(tickets) == 1
    ticket = tickets[0]
    assert ticket["protocol"] == "EMP-20260325-0001"
    assert (ticket["category"], ticket["category_label"]) == ("complaint", "Reclamação")
    assert ticket["summary"] == "Violão riscado." and ticket["order_id"] is None
    assert ticket["due_at"] == "2026-03-27T16:00:00"


# --- the trace of each tool -------------------------------------------------------------------


def trace(name, arguments, result):
    return trace_item(name, json.dumps(arguments), json.dumps(result))


@pytest.mark.parametrize(
    ("name", "arguments", "result", "kind", "title", "summary"),
    [
        (
            "search_products",
            {"category": "Violões", "max_price_brl": 1000},
            {"total_matches": 12, "returned": 10, "results": []},
            "data",
            "Buscou no catálogo",
            "Violões · até R$ 1.000 · 12 resultados",
        ),
        (
            "search_products",
            {"query": "saxofone"},
            {"total_matches": 0, "returned": 0, "results": []},
            "data",
            "Buscou no catálogo",
            "saxofone · nenhum resultado",
        ),
        (
            "search_products",
            {"string_type": "steel", "electroacoustic": True, "min_price_brl": 1000.5},
            {"total_matches": 1, "returned": 1, "results": []},
            "data",
            "Buscou no catálogo",
            "a partir de R$ 1.000,50 · aço · eletroacústico · 1 resultado",
        ),
        (
            "get_product",
            {"product_id": 96},
            {"found": True, "name": "Giannini GF-3D", "availability": "out_of_stock"},
            "data",
            "Abriu o produto",
            "Giannini GF-3D · esgotado",
        ),
        (
            "get_policy_sections",
            {"section_ids": ["4.1"]},
            {"sections": [{"id": "4.1", "title": "Direito de Arrependimento", "text": "x"}]},
            "policy",
            "Consultou o manual",
            "item 4.1 · Direito de Arrependimento",
        ),
        (
            "get_policy_sections",
            {"section_ids": ["3", "3.1"]},
            {
                "sections": [
                    {"id": "3", "title": "A", "text": ""},
                    {"id": "3.1", "title": "B", "text": ""},
                ]
            },
            "policy",
            "Consultou o manual",
            "itens 3, 3.1",
        ),
        (
            "verify_customer",
            {"order_id": 8, "contact": "ana@x.com"},
            {"verified": True, "customer_first_name": "Ana"},
            "identity",
            "Verificou a identidade",
            "pedido 8 · confirmado (Ana)",
        ),
        (
            "get_order_status",
            {"order_id": 8},
            {"order_id": 8, "status": "shipped"},
            "data",
            "Consultou o pedido",
            "pedido 8 · enviado",
        ),
        (
            "list_my_orders",
            {},
            {"orders": [{"order_id": 3}, {"order_id": 19}]},
            "data",
            "Listou os pedidos do cliente",
            "2 pedidos",
        ),
        (
            "check_return_eligibility",
            {"order_id": 7, "reason": "regret"},
            {"eligible": True, "reason": "regret", "reason_code": "ok", "deadline": "2026-02-24"},
            "rules",
            "Aplicou as regras de devolução",
            "arrependimento · elegível até 24/02",
        ),
        (
            "check_return_eligibility",
            {"order_id": 7, "reason": "defect"},
            {
                "eligible": False,
                "reason": "defect",
                "reason_code": "window_expired",
                "deadline": None,
            },
            "rules",
            "Aplicou as regras de devolução",
            "defeito · prazo vencido",
        ),
        (
            "open_handoff",
            {"category": "complaint", "summary": "x"},
            {"protocol": "EMP-20260325-0001", "due_at": "2026-03-27T16:00:00", "duplicate": False},
            "handoff",
            "Abriu atendimento humano",
            "EMP-20260325-0001 · resposta até 27/03 às 16:00",
        ),
        (
            "open_handoff",
            {"category": "return_request", "summary": "x", "order_id": 7},
            {"protocol": "EMP-1", "due_at": "2026-03-27T16:00:00", "duplicate": True},
            "handoff",
            "Abriu atendimento humano",
            "EMP-1 · já existia, resposta até 27/03 às 16:00",
        ),
    ],
)
def test_each_tool_has_a_kind_a_portuguese_title_and_a_summary(
    name, arguments, result, kind, title, summary
):
    item = trace(name, arguments, result)
    assert (item["kind"], item["title"], item["summary"]) == (kind, title, summary)
    assert item["ok"] is True and item["name"] == name


def test_the_contact_is_hidden_in_the_arguments():
    item = trace("verify_customer", {"order_id": 8, "contact": "ana@x.com"}, {"verified": True})
    assert item["arguments"] == {"order_id": 8, "contact": "(oculto)"}


def test_failures_are_marked_not_ok():
    failed = trace(
        "verify_customer", {"order_id": 8, "contact": "x"}, {"verified": False, "attempts_left": 2}
    )
    assert failed["ok"] is False and failed["summary"] == "pedido 8 · não confirmado"
    error = trace(
        "get_order_status", {"order_id": 8}, {"error": {"code": "not_verified", "message": "m"}}
    )
    assert error["ok"] is False and error["summary"] == "não verificado"
    missing = trace(
        "get_product",
        {"product_id": 9999},
        {"error": {"code": "product_not_found", "message": "m"}},
    )
    assert missing["ok"] is False


def test_long_results_are_cut_and_plain_text_is_kept():
    long = trace_item("get_policy_sections", "{}", json.dumps({"sections": [], "pad": "x" * 5000}))
    assert (
        long["truncated"] is True
        and isinstance(long["result"], str)
        and len(long["result"]) == 4000
    )
    text = trace_item("search_products", "{}", "not json at all")
    assert text["result"] == "not json at all" and text["ok"] is True and text["truncated"] is False
    bad_args = trace_item("get_product", "{oops", "{}")
    assert bad_args["arguments"] == "{oops"


def test_an_unknown_tool_still_gets_a_trace_item():
    item = trace_item("brand_new_tool", "{}", "{}")
    assert item["kind"] == "data" and item["title"] == "brand_new_tool"


# --- validation and security --------------------------------------------------------------------


def test_chat_input_validation():
    app, client = make_app()
    cases = [
        (post(app, "/api/chat", {"text": "oi"}, {"Host": HOST, "Content-Type": "text/plain"}), 415),
        (post(app, "/api/chat", {"text": "oi"}, {"Host": HOST}), 415),
        (post(app, "/api/chat", b"{not json"), 400),
        (post(app, "/api/chat", b"[1, 2]"), 400),
        (post(app, "/api/chat", {}), 400),
        (post(app, "/api/chat", {"text": 5}), 400),
        (post(app, "/api/chat", {"text": "   "}), 400),
        (post(app, "/api/chat", {"text": "a" * 2001}), 400),
        (post(app, "/api/chat", b"x" * (16 * 1024 + 1)), 413),
    ]
    for response, status in cases:
        assert response.status == status, response.body
        assert "error" in body(response)
    assert client.calls == []  # nothing reached the model
    assert app.sessions.load_messages(app.session_id) == []


def test_text_at_the_limit_is_accepted():
    app, _ = make_app([assistant_text("ok")])
    assert post(app, "/api/chat", {"text": "a" * 2000}).status == 200


def test_wrong_methods_and_routes():
    app, _ = make_app()
    assert get(app, "/api/chat").status == 405
    assert post(app, "/api/state", {}).status == 405
    assert post(app, "/api/handoffs", {}).status == 405
    assert post(app, "/api/nope", {}).status == 404
    assert app.handle("DELETE", "/api/state", {"Host": HOST}, b"").status == 405


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Host": "evil.example"},
        {"Host": "evil.example:8765"},
        {"Host": "127.0.0.1:9999"},
        {"Host": "127.0.0.1"},
        {"Host": HOST, "Origin": "http://evil.example"},
        {"Host": HOST, "Origin": "http://127.0.0.1:9999"},
        {"Host": HOST, "Origin": "null"},
    ],
)
def test_requests_from_other_hosts_or_origins_are_refused_before_anything_runs(headers):
    app, client = make_app([assistant_text("never")])
    headers = {**headers, "Content-Type": "application/json"}
    for method, path in (("GET", "/"), ("GET", "/api/state"), ("POST", "/api/chat")):
        response = app.handle(method, path, headers, json.dumps({"text": "oi"}).encode())
        assert response.status == 403, (method, path)
    assert client.calls == []


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "localhost:8765"},
        {"Host": "LOCALHOST:8765"},
        {"Host": HOST, "Origin": "http://127.0.0.1:8765"},
        {"Host": HOST, "Origin": "http://localhost:8765"},
    ],
)
def test_local_hosts_and_the_same_origin_are_accepted(headers):
    app, _ = make_app()
    assert app.handle("GET", "/api/state", headers, b"").status == 200


# --- failures ---------------------------------------------------------------------------------


class ExplodingClient:
    def chat(self, messages, tools):
        raise RuntimeError("secret-internal-detail")


def test_a_model_failure_is_a_short_502_and_saves_nothing():
    app, _ = make_app(client=ExplodingClient())
    response = post(app, "/api/chat", {"text": "oi"})
    assert response.status == 502
    message = body(response)["error"]
    assert "secret-internal-detail" not in message and "Traceback" not in message and message
    assert app.sessions.load_messages(app.session_id) == []
    assert body(get(app, "/api/state"))["turns"] == []


# --- a real HTTP round trip ---------------------------------------------------------------------


def test_the_real_server_answers_over_http_on_a_free_local_port():
    # Like `emporio web`: the app and the server share a thread; the client runs in another one.
    app, _ = make_app([assistant_text("Olá! Sou a Melô.")])
    server = make_server(app, 0)
    port = server.server_address[1]
    assert server.server_address[0] == "127.0.0.1" and app.port == port
    seen = {}

    def client():
        try:
            base = f"http://127.0.0.1:{port}"
            with urllib.request.urlopen(base + "/") as page:
                seen["page"] = (page.status, page.read())
            request = urllib.request.Request(
                base + "/api/chat",
                data=json.dumps({"text": "oi"}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request) as reply:
                seen["reply"] = json.loads(reply.read())["reply"]
            wrong_host = urllib.request.Request(
                base + "/api/state", headers={"Host": "evil.example"}
            )
            try:
                urllib.request.urlopen(wrong_host)
            except urllib.error.HTTPError as refused:
                seen["refused"] = refused.code
        except (OSError, ValueError, KeyError) as error:  # reported by the assertions below
            seen["error"] = repr(error)
        finally:
            server.shutdown()

    thread = threading.Thread(target=client, daemon=True)
    thread.start()
    server.serve_forever()
    server.server_close()
    thread.join(timeout=5)

    assert "error" not in seen, seen["error"]
    assert seen["page"][0] == 200 and "Melô".encode() in seen["page"][1]
    assert seen["reply"] == "Olá! Sou a Melô."
    assert seen["refused"] == 403


def test_the_side_panel_can_be_collapsed_at_every_width():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    sheet = (STATIC_DIR / "app.css").read_text(encoding="utf-8")
    # the controls exist on every width (they used to be marked as narrow-only)
    assert "only-narrow" not in html
    assert 'id="btn-panel"' in html and 'aria-expanded="true"' in html
    assert 'aria-label="Recolher painel"' in html
    # the choice is remembered, and the page collapses on wide screens too
    assert "emporio-panel" in script
    assert 'body[data-panel="closed"] .side' in sheet


def test_a_collapsed_panel_leaves_a_visible_tab_and_the_button_has_an_icon():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    sheet = (STATIC_DIR / "app.css").read_text(encoding="utf-8")
    assert 'id="panel-tab"' in html
    assert (
        "badge" not in html + script + sheet
    )  # no counters on the button, the tab or the panel tabs
    assert (
        'class="pane-fill"' in html
    )  # the icon of the header button, inline so the CSS reaches it
    assert ".panel-tab" in sheet and 'body[data-panel="closed"] .panel-tab' in sheet
    assert '[aria-expanded="false"] .pane-fill' in sheet
    assert "#panel-tab" in script
