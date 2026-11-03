"""Spec 17: the MCP server (JSON-RPC over stdio) that exposes the agent tools."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from emporio import cli
from emporio.data import load_store_data
from emporio.db import HandoffStore, SessionStore, connect
from emporio.mcp_server import LATEST_PROTOCOL, McpServer, serve
from emporio.policies import load_policy_sections
from emporio.session import SessionState
from emporio.tools import TOOL_NAMES, ToolContext, Toolset

ROOT = Path(__file__).resolve().parents[1]
DATA = load_store_data(ROOT / "data")
POLICIES = load_policy_sections(ROOT / "data" / "políticas_da_loja.pdf")
NOW = datetime(2026, 3, 25, 10, 0)
CLIENT = {"name": "t", "version": "1"}


def make_server() -> McpServer:
    conn = connect(":memory:")
    session_id = SessionStore(conn).create_session("mcp", date(2026, 3, 25), NOW)
    context = ToolContext(DATA, POLICIES, SessionState(), HandoffStore(conn), session_id, NOW)
    return McpServer(Toolset(context))


def request(method, params=None, id_=1):
    message = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        message["params"] = params
    return message


def init_params(version="2025-06-18"):
    return {"protocolVersion": version, "capabilities": {}, "clientInfo": CLIENT}


def initialize(server, version="2025-06-18"):
    return server.handle(request("initialize", init_params(version)))


def call(server, name, arguments, id_=2):
    return server.handle(request("tools/call", {"name": name, "arguments": arguments}, id_))


def payload(response):
    """The JSON object a tool returned, from the text content item."""
    return json.loads(response["result"]["content"][0]["text"])


# --- RF-01 / RF-02 handshake and lifecycle -----------------------------------------------------


def test_initialize_negotiates_the_version_and_declares_the_tools_capability():
    server = make_server()
    result = initialize(server)["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] and result["serverInfo"]["version"]


def test_an_older_supported_version_is_kept_and_an_unknown_one_gets_the_latest():
    assert initialize(make_server(), "2024-11-05")["result"]["protocolVersion"] == "2024-11-05"
    assert initialize(make_server(), "1999-01-01")["result"]["protocolVersion"] == LATEST_PROTOCOL


def test_ping_works_anytime_and_other_requests_wait_for_initialize():
    server = make_server()
    assert server.handle(request("ping"))["result"] == {}
    early = server.handle(request("tools/list"))
    assert early["error"]["code"] == -32002
    initialize(server)
    assert "result" in server.handle(request("tools/list"))


# --- RF-03 / RF-04 tools -----------------------------------------------------------------------


def test_tools_list_has_every_tool_with_a_schema():
    server = make_server()
    initialize(server)
    tools = server.handle(request("tools/list"))["result"]["tools"]
    assert [t["name"] for t in tools] == list(TOOL_NAMES)
    for tool in tools:
        assert tool["description"] and tool["inputSchema"]["type"] == "object"


def test_a_catalog_call_returns_one_text_item_with_the_json_result():
    server = make_server()
    initialize(server)
    response = call(server, "search_products", {"query": "takamine"})
    content = response["result"]["content"]
    assert len(content) == 1 and content[0]["type"] == "text"
    assert response["result"]["isError"] is False
    assert payload(response)["results"]


def test_a_tool_error_is_flagged_with_is_error():
    server = make_server()
    initialize(server)
    response = call(server, "get_order_status", {"order_id": 8})
    assert response["result"]["isError"] is True
    assert payload(response)["error"]["code"] == "not_verified"


# --- RF-05 the verification state lives with the process ---------------------------------------


def test_verification_then_order_status_works_and_a_wrong_contact_does_not():
    server = make_server()
    initialize(server)
    bad = call(server, "verify_customer", {"order_id": 8, "contact": "errado@exemplo.com"})
    assert payload(bad)["verified"] is False
    assert call(server, "get_order_status", {"order_id": 8})["result"]["isError"] is True
    arguments = {"order_id": 8, "contact": "anacarol.ferreira@coldmail.com"}
    assert payload(call(server, "verify_customer", arguments))["verified"] is True
    status = call(server, "get_order_status", {"order_id": 8})
    assert status["result"]["isError"] is False
    assert payload(status)["tracking_code"]


def test_the_policy_search_tool_is_exposed():
    server = make_server()
    initialize(server)
    found = payload(call(server, "search_policies", {"query": "prazo para devolver"}))
    assert found["method"] in {"bm25", "hybrid"} and found["sections"]


# --- RF-06 errors ------------------------------------------------------------------------------


def test_protocol_errors_have_the_standard_codes():
    server = make_server()
    initialize(server)
    assert call(server, "no_such_tool", {})["error"]["code"] == -32602
    assert server.handle(request("no/such/method"))["error"]["code"] == -32601
    missing = server.handle(request("tools/call", {"arguments": {}}))
    assert missing["error"]["code"] == -32602
    bad_args = server.handle(request("tools/call", {"name": "search_products", "arguments": []}))
    assert bad_args["error"]["code"] == -32602


def test_notifications_get_no_response_and_responses_keep_the_request_id():
    server = make_server()
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert server.handle(request("ping", id_="abc"))["id"] == "abc"


# --- RF-07 serving lines -----------------------------------------------------------------------


def test_serve_answers_line_by_line_and_survives_bad_input():
    server = make_server()
    lines = [
        json.dumps(request("initialize", init_params())),
        "",
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        "this is not json",
        json.dumps(request("tools/list", id_=3)),
    ]
    written: list[str] = []
    serve(server, iter(lines), written.append)
    replies = [json.loads(line) for line in written]
    assert [r.get("id") for r in replies] == [1, None, 3]
    assert replies[1]["error"]["code"] == -32700
    assert all("\n" not in line for line in written)
    assert replies[2]["result"]["tools"]


# --- RF-08 the command -------------------------------------------------------------------------


def test_the_mcp_command_serves_stdin_and_writes_only_protocol_lines(tmp_path):
    env = {
        "EMPORIO_DB_PATH": str(tmp_path / "var" / "e.db"),
        "EMPORIO_TODAY": "2026-03-25",
        "EMPORIO_EMBEDDINGS": "off",
    }
    feed = iter(
        [
            json.dumps(request("initialize", init_params())),
            json.dumps(request("tools/list", id_=2)),
        ]
    )

    def read(_prompt):
        try:
            return next(feed)
        except StopIteration:
            raise EOFError from None

    written: list[str] = []
    code = cli.main(
        ["mcp"], env=env, client_factory=lambda s: None, read=read, write=written.append
    )
    assert code == 0
    assert len(written) == 2
    assert all(json.loads(line)["jsonrpc"] == "2.0" for line in written)


def test_mcp_is_a_known_command():
    assert "mcp" in cli.COMMANDS
    assert cli.build_parser().parse_args(["mcp"]).command == "mcp"


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_every_tool_rejects_unexpected_arguments_with_a_tool_error(name):
    server = make_server()
    initialize(server)
    response = call(server, name, {"unexpected_argument": 1})
    assert response["result"]["isError"] is True
