import inspect
import json
from datetime import datetime
from pathlib import Path

import pytest

from emporio import tools as tools_module
from emporio.data import load_store_data
from emporio.db import HANDOFF_CATEGORIES, HandoffStore, connect
from emporio.policies import load_policy_sections
from emporio.session import SessionState
from emporio.tools import TOOL_NAMES, ToolContext, Toolset

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 3, 25, 10, 0)


@pytest.fixture(scope="module")
def data():
    return load_store_data(ROOT / "data")


@pytest.fixture(scope="module")
def policies():
    return load_policy_sections(ROOT / "data" / "políticas_da_loja.pdf")


@pytest.fixture
def toolset(data, policies):
    conn = connect(":memory:")
    ctx = ToolContext(
        data=data,
        policies=policies,
        state=SessionState(),
        handoffs=HandoffStore(conn),
        session_id=None,
        now=NOW,
    )
    yield Toolset(ctx)
    conn.close()


def run(toolset, name, **arguments):
    return json.loads(toolset.call(name, json.dumps(arguments)))


def test_schemas_expose_the_eight_tools(toolset):
    names = [s["function"]["name"] for s in toolset.schemas]
    assert names == list(TOOL_NAMES) and len(names) == 8
    for schema in toolset.schemas:
        assert schema["type"] == "function"
        parameters = schema["function"]["parameters"]
        assert parameters["type"] == "object" and parameters["additionalProperties"] is False
        assert schema["function"]["description"]


def test_every_schema_parameter_exists_in_the_wrapped_function(toolset):
    for name, tool in toolset._tools.items():
        signature = inspect.signature(tool.function)
        properties = tool.parameters["properties"]
        assert set(properties) <= set(signature.parameters), name
        for required in tool.parameters["required"]:
            assert signature.parameters[required].default is inspect.Parameter.empty, name
        injected = set(tool.inject(toolset._ctx)) | set(tool.defaults)
        mandatory = {
            p.name
            for p in signature.parameters.values()
            if p.default is inspect.Parameter.empty and p.kind is not p.VAR_KEYWORD
        }
        assert mandatory <= set(properties) | injected, name


def test_enums_come_from_the_real_values(toolset, data):
    by_name = {
        s["function"]["name"]: s["function"]["parameters"]["properties"] for s in toolset.schemas
    }
    assert by_name["search_products"]["category"]["enum"] == list(data.categories["name"])
    assert by_name["check_return_eligibility"]["reason"]["enum"] == [
        "regret",
        "defect",
        "preference",
    ]
    assert by_name["open_handoff"]["category"]["enum"] == list(HANDOFF_CATEGORIES)


def test_no_tool_can_look_up_customers(toolset):
    forbidden = {"customer_id", "customer", "customer_name", "name", "email", "phone"}
    for schema in toolset.schemas:
        assert not forbidden & set(schema["function"]["parameters"]["properties"])


def test_catalog_call_returns_unescaped_json(toolset):
    raw = toolset.call("search_products", '{"max_price_brl": 1000, "category": "Violões"}')
    assert "Violões" in raw
    result = json.loads(raw)
    assert result["results"] and all(r["price_brl"] <= 1000 for r in result["results"])


def test_policy_call(toolset):
    result = run(toolset, "get_policy_sections", section_ids=["4.1"])
    assert [s["id"] for s in result["sections"]] == ["4.1"]


def test_context_is_injected_so_state_persists_across_calls(toolset):
    assert run(toolset, "get_order_status", order_id=8)["error"]["code"] == "not_verified"
    verified = run(toolset, "verify_customer", order_id=8, contact="anacarol.ferreira@coldmail.com")
    assert verified["verified"] is True
    status = run(toolset, "get_order_status", order_id=8)
    assert status["status"] == "shipped" and status["estimated_delivery_passed"] is True
    assert run(toolset, "list_my_orders")["orders"][0]["order_id"] == 8


def test_handoff_call_uses_the_default_order_and_the_injected_clock(toolset):
    result = run(toolset, "open_handoff", category="complaint", summary="Violão chegou riscado.")
    assert result["protocol"] == "EMP-20260325-0001"
    assert result["due_at"] == "2026-03-27T16:00:00"
    assert result["duplicate"] is False


@pytest.mark.parametrize(
    ("name", "arguments", "code"),
    [
        ("search_products", "{", "invalid_argument"),
        ("search_products", "[]", "invalid_argument"),
        ("nope", "{}", "unknown_tool"),
        ("get_product", "{}", "invalid_argument"),
        ("get_product", '{"product_id": "95"}', "invalid_argument"),
        ("get_product", '{"product_id": true}', "invalid_argument"),
        ("get_product", '{"product_id": 95, "data": 1}', "invalid_argument"),
        (
            "open_handoff",
            '{"category": "complaint", "summary": "x", "session_id": "evil"}',
            "invalid_argument",
        ),
        ("check_return_eligibility", '{"order_id": 7, "reason": "other"}', "invalid_argument"),
        ("search_products", '{"limit": 2.5}', "invalid_argument"),
        ("get_policy_sections", '{"section_ids": "4.1"}', "invalid_argument"),
    ],
)
def test_bad_calls_come_back_as_error_json(toolset, name, arguments, code):
    result = json.loads(toolset.call(name, arguments))
    assert result["error"]["code"] == code


def test_empty_arguments_string_means_no_arguments(toolset):
    assert "orders" not in json.loads(toolset.call("list_my_orders", ""))


def test_exceptions_inside_a_tool_propagate(monkeypatch, data, policies):
    def boom(data, **kwargs):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(tools_module.catalog, "search_products", boom)
    conn = connect(":memory:")
    ctx = ToolContext(data, policies, SessionState(), HandoffStore(conn), None, NOW)
    with pytest.raises(RuntimeError, match="disk on fire"):
        Toolset(ctx).call("search_products", "{}")
    conn.close()
