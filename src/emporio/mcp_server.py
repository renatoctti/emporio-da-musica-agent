"""A Model Context Protocol server for the agent tools, over standard input and output.

MCP is JSON-RPC 2.0 with one message per line for the stdio transport. A tools-only server needs a
handful of methods (initialize, ping, tools/list, tools/call), so it is written by hand, like the
agent loop, instead of pulling a framework. The rules do not change: the tools still refuse order
data until verify_customer succeeded, and that state lives as long as the server process.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from importlib import metadata
from typing import Any

from emporio.tools import Toolset

LATEST_PROTOCOL = "2025-06-18"
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_NAME = "emporio-melo"
INSTRUCTIONS = (
    "Tools of the virtual assistant of Empório da Música, a musical-instrument store. Order data "
    "and returns need verify_customer (order number plus the e-mail or phone on that order) first."
)

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
NOT_INITIALIZED = -32002


def _server_version() -> str:
    try:
        return metadata.version("emporio-agent")
    except metadata.PackageNotFoundError:
        return "0.1.0"


def _failure(id_: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


class McpServer:
    def __init__(self, toolset: Toolset) -> None:
        self._toolset = toolset
        self._initialized = False

    def handle(self, message: Any) -> dict[str, Any] | None:
        """The response to one message, or None for a notification (which never gets one)."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _failure(None, INVALID_REQUEST, "Send a JSON-RPC 2.0 message object.")
        method = message.get("method")
        if not isinstance(method, str):
            return None  # a response from the client; this server never sends requests
        if "id" not in message:
            return None  # a notification, such as notifications/initialized
        id_ = message["id"]
        params = message.get("params")
        if params is not None and not isinstance(params, dict):
            return _failure(id_, INVALID_PARAMS, "params must be an object.")
        params = params or {}

        if method == "ping":
            return {"jsonrpc": "2.0", "id": id_, "result": {}}
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": id_, "result": self._initialize(params)}
        if not self._initialized:
            return _failure(id_, NOT_INITIALIZED, "Send initialize first.")
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": id_, "result": {"tools": self._tools()}}
        if method == "tools/call":
            return self._call(id_, params)
        return _failure(id_, METHOD_NOT_FOUND, f"Unknown method {method!r}.")

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        self._initialized = True
        asked = params.get("protocolVersion")
        return {
            "protocolVersion": asked if asked in SUPPORTED_PROTOCOLS else LATEST_PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": _server_version()},
            "instructions": INSTRUCTIONS,
        }

    def _tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": schema["function"]["name"],
                "description": schema["function"]["description"],
                "inputSchema": schema["function"]["parameters"],
            }
            for schema in self._toolset.schemas
        ]

    def _call(self, id_: Any, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments", {})
        known = {tool["name"] for tool in self._tools()}
        if not isinstance(name, str) or name not in known:
            return _failure(id_, INVALID_PARAMS, f"Unknown tool {name!r}.")
        if not isinstance(arguments, dict):
            return _failure(id_, INVALID_PARAMS, "arguments must be an object.")
        text = self._toolset.call(name, json.dumps(arguments))
        try:
            is_error = "error" in json.loads(text)
        except (ValueError, TypeError):
            is_error = False
        result = {"content": [{"type": "text", "text": text}], "isError": is_error}
        return {"jsonrpc": "2.0", "id": id_, "result": result}


def serve(
    server: McpServer,
    lines: Iterable[str],
    write: Callable[[str], None],
    flush: Callable[[], None] | None = None,
) -> None:
    """Answer one message per line until the input ends. stdout must carry nothing else."""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            response: dict[str, Any] | None = _failure(None, PARSE_ERROR, "Invalid JSON.")
        else:
            response = server.handle(message)
        if response is not None:
            write(json.dumps(response))  # ensure_ascii keeps it on one line and encoding-proof
            if flush is not None:
                flush()
