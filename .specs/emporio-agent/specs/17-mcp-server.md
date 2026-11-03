# Spec 17: MCP server

**Status:** 🟢 Implemented
**Author:** renatoctti
**Date:** 2026-11-02
**Scope:** expose the agent tools through the Model Context Protocol (stdio) and a command to run it
**Depends on:** 06, 07, 08, 09, 13
**Delivery:** autonomous (after its dependencies)

---

## Summary

The agent tools (catalog, manual search and sections, identity check, order status, return rules,
human handoff) are plain functions behind a schema. This spec exposes the same tools to any
Model Context Protocol client, such as Claude Desktop or an IDE, with the command emporio mcp. The
rules do not change: a client still has to pass the identity check before any order data.

## Context

The protocol is small for a tools-only server: JSON-RPC 2.0 messages, one per line, over standard
input and output. It is written by hand in the same spirit as the agent loop (no framework), so
there is no new dependency. The module was also checked once against the official Python SDK client;
that client is not a dependency of the project.

---

## Allowed files

**Production**

- src/emporio/mcp_server.py (new): McpServer, serve
- src/emporio/cli.py: the mcp command

**Tests:** tests/test_mcp.py (new)

**Docs:** README.md, PROJECT_MAP.md

**Do not touch:** the tools and the agent loop.

---

## Functional requirements

| ID | Requirement | Priority | Acceptance |
|---|---|---|---|
| ✅ RF-01 | initialize answers with the negotiated protocol version (the client version when supported, the latest one otherwise), the tools capability and the server name and version | Must | Unit tests |
| ✅ RF-02 | ping answers an empty result at any time; every other request before initialize is a JSON-RPC error | Must | Unit tests |
| ✅ RF-03 | tools/list returns every tool of the agent with name, description and inputSchema | Must | Names equal TOOL_NAMES |
| ✅ RF-04 | tools/call runs the tool and returns one text content item with the JSON result; isError is true when the result is an error object | Must | Catalog call, unverified order call |
| ✅ RF-05 | The verification state lives for the whole server process, so verify_customer followed by get_order_status works and a wrong order does not | Must | Sequence test |
| ✅ RF-06 | An unknown tool name is a JSON-RPC error -32602; an unknown method is -32601; invalid JSON is -32700 with a null id; notifications get no response | Must | Unit tests |
| ✅ RF-07 | serve reads one message per line, ignores blank lines, writes one response per line without embedded newlines, and stops at the end of the input | Must | Stream test |
| ✅ RF-08 | emporio mcp starts the server with the same data, manual, retriever and database as the other commands; stdout carries only protocol messages | Must | Command test |

## Non-functional requirements

- No new dependency; no network access beyond what the tools already do (the embeddings call is optional).
- The server is for local use through stdio: it opens no port.
- Personal data is returned only through the tools, after the same identity check as the chat.

## Out of scope

- Resources, prompts, logging and sampling capabilities; progress notifications; HTTP transports.
- Authentication beyond the identity check of the tools.

## Test checklist

- [x] ✅ Handshake, lifecycle and errors
- [x] ✅ Tool listing and calls, including the verification sequence
- [x] ✅ Line-based serving and the command
