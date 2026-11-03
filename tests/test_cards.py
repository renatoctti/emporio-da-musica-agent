"""Spec 22: the card models that the page draws from the trace of an answer (cards.js, run by Node)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.fakes import assistant_calls, assistant_text, tool_call
from tests.test_web import chat, make_app

RUNNER = Path(__file__).parent / "js" / "run_cards.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")


def run(trace):
    done = subprocess.run(
        ["node", str(RUNNER)],
        input=json.dumps(trace),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=30,
    )
    return json.loads(done.stdout)


def real_trace(*calls):
    """The trace the page really receives: the tools run for real, the model is scripted."""
    app, _ = make_app([assistant_calls(*calls), assistant_text("ok")])
    return chat(app, "pergunta")["trace"]


def item(name, result, *, ok=True, truncated=False, arguments=None):
    return {
        "name": name,
        "kind": "data",
        "title": name,
        "summary": "",
        "arguments": arguments or {},
        "result": result,
        "truncated": truncated,
        "ok": ok,
    }


def price(**over):
    base = {
        "list_price_brl": 1099.0,
        "promotion": {"discount_percent": 20},
        "price_brl": 879.2,
        "pix_price_brl": 879.2,
        "pix_note": "x",
        "installments": {
            "max": 5,
            "options": [{"n": 1, "installment_brl": 879.2}, {"n": 5, "installment_brl": 175.84}],
        },
    }
    return {**base, **over}


def product(**over):
    base = {
        "found": True,
        "product_id": 7,
        "name": "Ohana CK-20 Concert Natural",
        "brand": "Ohana",
        "category": "Ukuleles",
        "availability": "in_stock",
        "stock_quantity": 3,
        "price": price(),
    }
    return {**base, **over}


# --- product ---------------------------------------------------------------------------------


def test_a_real_product_result_becomes_a_product_card_with_the_numbers_of_the_result():
    trace = real_trace(tool_call("c1", "get_product", {"product_id": 95}))
    result = trace[0]["result"]
    out = run(trace)
    (card,) = out["cards"]
    assert card["type"] == "product" and card["name"] == result["name"]
    assert (
        card["price"] == "R$ 2.199,00" and card["list_price"] is None and card["discount"] is None
    )
    options = result["price"]["installments"]["options"]
    best = options[-1]
    cents = f"{best['installment_brl']:.2f}".replace(".", ",")
    assert card["installment"] == f"até {best['n']}x de R$ {cents} sem juros"
    assert card["pix"] == "No PIX: R$ 2.089,05"
    assert card["stock"] == f"{result['stock_quantity']} em estoque"


def test_a_promotion_shows_the_list_price_the_percent_and_no_extra_pix_discount():
    (card,) = run([item("get_product", product())])["cards"]
    assert card["list_price"] == "R$ 1.099,00" and card["price"] == "R$ 879,20"
    assert card["discount"] == "20% off"
    assert card["installment"] == "até 5x de R$ 175,84 sem juros"
    assert card["pix"] == "PIX: sem desconto extra"


def test_a_product_that_is_out_of_stock_says_so_and_has_no_installment_when_there_are_no_options():
    out = run(
        [
            item(
                "get_product",
                product(
                    availability="out_of_stock",
                    stock_quantity=0,
                    price=price(promotion=None, installments={"max": 1, "options": []}),
                ),
            )
        ]
    )
    (card,) = out["cards"]
    assert card["stock"] == "Esgotado" and card["discount"] is None and card["installment"] is None


# --- product list ----------------------------------------------------------------------------


def test_a_real_search_becomes_a_list_of_at_most_four_items_and_counts_the_rest():
    trace = real_trace(
        tool_call("c1", "search_products", {"query": "violao", "max_price_brl": 1000})
    )
    result = trace[0]["result"]
    (card,) = run(trace)["cards"]
    assert card["type"] == "products" and len(card["items"]) == min(4, len(result["results"]))
    assert card["items"][0]["name"] == result["results"][0]["name"]
    assert card["more"] == result["total_matches"] - len(card["items"])


def test_a_list_that_only_repeats_the_product_cards_is_dropped():
    found = {
        "product_id": 7,
        "name": "Ohana",
        "category": "Ukuleles",
        "list_price_brl": 549.0,
        "price_brl": 439.2,
        "promotion": None,
        "availability": "in_stock",
        "stock_quantity": 6,
    }
    search = item("search_products", {"total_matches": 1, "returned": 1, "results": [found]})
    assert [c["type"] for c in run([search, item("get_product", product())])["cards"]] == [
        "product"
    ]
    other = {**found, "product_id": 8}
    both = item("search_products", {"total_matches": 2, "returned": 2, "results": [found, other]})
    assert [c["type"] for c in run([both, item("get_product", product())])["cards"]] == [
        "products",
        "product",
    ]


def test_an_empty_search_gives_no_card():
    assert (
        run([item("search_products", {"total_matches": 0, "returned": 0, "results": []})])["cards"]
        == []
    )


# --- order -----------------------------------------------------------------------------------


def order(status, **over):
    base = {
        "order_id": 8,
        "status": status,
        "status_meaning": "x",
        "order_date": "2026-02-15",
        "total_brl": 349.9,
        "payment": {"method": "credit", "installments": 6},
        "items": [{"product_id": 120, "name": "Kala KA-C Concert Mogno", "quantity": 2}],
        "tracking_code": "BRJL5544332BR",
        "estimated_delivery": "2026-02-28",
        "estimated_delivery_passed": False,
    }
    return {**base, **over}


def steps(status):
    (card,) = run([item("get_order_status", order(status))])["cards"]
    return [(s["label"], s["state"]) for s in card["steps"]]


def test_a_real_order_becomes_a_shipped_order_card_with_a_late_estimate():
    trace = real_trace(
        tool_call(
            "c1", "verify_customer", {"order_id": 8, "contact": "anacarol.ferreira@coldmail.com"}
        ),
        tool_call("c2", "get_order_status", {"order_id": 8}),
    )
    out = run(trace)
    (card,) = out["cards"]  # the identity check itself is not drawn
    assert card["type"] == "order" and card["order_id"] == 8
    assert card["steps"] == [
        {"label": "Confirmado", "state": "done"},
        {"label": "Enviado", "state": "current"},
        {"label": "Entregue", "state": "todo"},
    ]
    assert card["tracking_code"] == "BRJL5544332BR" and card["estimate"] == "28/02/2026"
    assert card["late"] is True and card["total"] == "R$ 349,90"
    assert card["items"] == ["1× Kala KA-C Concert Mogno"]
    assert card["payment"] == "Cartão de débito"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("pending", [("Confirmado", "todo"), ("Enviado", "todo"), ("Entregue", "todo")]),
        ("confirmed", [("Confirmado", "current"), ("Enviado", "todo"), ("Entregue", "todo")]),
        ("shipped", [("Confirmado", "done"), ("Enviado", "current"), ("Entregue", "todo")]),
        ("delivered", [("Confirmado", "done"), ("Enviado", "done"), ("Entregue", "done")]),
        ("cancelled", [("Cancelado", "current")]),
    ],
)
def test_the_steps_follow_the_status(status, expected):
    assert steps(status) == expected


def test_payment_texts_and_a_missing_tracking_code():
    texts = {}
    for method, installments in (("pix", None), ("boleto", None), ("credit", 6), ("credit", 1)):
        result = order(
            "confirmed",
            payment={"method": method, "installments": installments},
            tracking_code=None,
            estimated_delivery=None,
        )
        (card,) = run([item("get_order_status", result)])["cards"]
        texts[(method, installments)] = card["payment"]
        assert card["tracking_code"] is None and card["estimate"] is None
    assert texts == {
        ("pix", None): "PIX",
        ("boleto", None): "Boleto",
        ("credit", 6): "Cartão de crédito em 6x",
        ("credit", 1): "Cartão de crédito à vista",
    }


# --- ticket and sources ----------------------------------------------------------------------


def test_a_real_handoff_becomes_a_ticket_card():
    trace = real_trace(
        tool_call("c1", "open_handoff", {"category": "complaint", "summary": "Violão riscado."})
    )
    (card,) = run(trace)["cards"]
    assert card == {
        "type": "ticket",
        "protocol": trace[0]["result"]["protocol"],
        "category": "Reclamação",
        "due": "27/03 às 16:00",
        "status": "Aberto",
        "duplicate": False,
    }


def test_a_duplicate_ticket_says_it_already_existed():
    result = {
        "protocol": "EMP-20260325-0001",
        "category": "defect",
        "status": "open",
        "due_at": "2026-03-27T16:00:00",
        "duplicate": True,
    }
    (card,) = run([item("open_handoff", result)])["cards"]
    assert card["duplicate"] is True and card["category"] == "Defeito"


def test_policy_sections_become_one_sources_card_and_an_empty_search_gives_none():
    sections = [
        {"id": "4.1", "title": "Troca por defeito", "text": "..."},
        {"id": "8.1", "title": "Garantia", "text": "..."},
    ]
    out = run(
        [
            item("search_policies", {"method": "hybrid", "sections": sections}),
            item("get_policy_sections", {"sections": sections[:1]}),
        ]
    )
    assert [c["type"] for c in out["cards"]] == ["sources"]  # one card, ids merged and not repeated
    assert out["cards"][0]["items"] == [
        {"id": "4.1", "title": "Troca por defeito"},
        {"id": "8.1", "title": "Garantia"},
    ]
    assert run([item("search_policies", {"method": "bm25", "sections": []})])["cards"] == []


# --- no card ---------------------------------------------------------------------------------


def test_failures_truncated_results_and_other_tools_give_no_card():
    cut = item("get_product", '{"found": true, "name": "x', truncated=True)
    failed = item("get_order_status", {"error": {"code": "not_verified", "message": "m"}}, ok=False)
    others = [
        item("verify_customer", {"verified": True, "customer_first_name": "Ana"}),
        item("list_my_orders", {"orders": [{"order_id": 8}]}),
        item("check_return_eligibility", {"eligible": True}),
        item("unknown_tool", {"x": 1}),
        item("get_product", {"found": False}),
    ]
    assert run([cut, failed, *others])["cards"] == []


def test_the_cards_keep_the_order_of_the_calls():
    trace = [
        item("get_product", product()),
        item(
            "open_handoff",
            {
                "protocol": "P",
                "category": "other",
                "due_at": "2026-03-27T16:00:00",
                "duplicate": False,
            },
        ),
    ]
    assert [c["type"] for c in run(trace)["cards"]] == ["product", "ticket"]


# --- follow-up questions ---------------------------------------------------------------------


def test_follow_ups_depend_on_the_kinds_of_cards_and_are_at_most_three():
    assert run([])["followUps"] == []
    product_ups = run([item("get_product", product())])["followUps"]
    assert "Quais as formas de pagamento?" in product_ups and 1 <= len(product_ups) <= 3
    order_ups = run([item("get_order_status", order("shipped"))])["followUps"]
    assert "Como faço para devolver?" in order_ups
    ticket = item(
        "open_handoff",
        {"protocol": "P", "category": "other", "due_at": "2026-03-27T16:00:00", "duplicate": False},
    )
    assert run([ticket])["followUps"] == []
    many = run([item("get_product", product()), item("get_order_status", order("shipped"))])[
        "followUps"
    ]
    assert len(many) <= 3 and len(set(many)) == len(many)
