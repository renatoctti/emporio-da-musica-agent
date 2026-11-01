"""Exposes the domain functions to the model as function-calling tools.

The schemas are the contract between the agent loop and the tools. Everything the model must not
control (the data, the verification state, the clock, the session id) is injected here, and the
arguments the model sends are validated against the schema before any function runs.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from emporio import catalog, handoff, orders, policies, returns
from emporio.data import StoreData
from emporio.db import HANDOFF_CATEGORIES, HandoffStore
from emporio.policies import PolicySection
from emporio.results import error
from emporio.session import SessionState

TOOL_NAMES: tuple[str, ...] = (
    "search_products",
    "get_product",
    "get_policy_sections",
    "verify_customer",
    "get_order_status",
    "list_my_orders",
    "check_return_eligibility",
    "open_handoff",
)

_TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list) and all(isinstance(i, str) for i in v),
}


@dataclass
class ToolContext:
    data: StoreData
    policies: tuple[PolicySection, ...]
    state: SessionState
    handoffs: HandoffStore
    session_id: str | None
    now: datetime


@dataclass(frozen=True)
class _Tool:
    function: Callable[..., dict[str, Any]]
    description: str
    parameters: dict[str, Any]
    inject: Callable[[ToolContext], dict[str, Any]]
    defaults: dict[str, Any] = field(default_factory=dict)


def _object(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def _build_tools(ctx: ToolContext) -> dict[str, _Tool]:
    order_id = {"type": "integer", "description": "Order number given by the customer."}
    return {
        "search_products": _Tool(
            function=catalog.search_products,
            description=(
                "Search the store catalog. Prices are the current prices (active promotion "
                "applied). Without a query it lists only products available now; with a query "
                "it also finds unavailable products by name so you can explain their status."
            ),
            parameters=_object(
                {
                    "query": {
                        "type": "string",
                        "description": "Words from the product name, brand or description.",
                    },
                    "category": {
                        "type": "string",
                        "enum": list(ctx.data.categories["name"]),
                        "description": "Exact category name, e.g. 'Violões' for acoustic guitars.",
                    },
                    "min_price_brl": {"type": "number"},
                    "max_price_brl": {"type": "number"},
                    "string_type": {"type": "string", "enum": list(catalog.STRING_TYPES)},
                    "electroacoustic": {"type": "boolean"},
                    "available_only": {"type": "boolean"},
                    "limit": {"type": "integer", "description": "1 to 10, default 5."},
                }
            ),
            inject=lambda c: {"data": c.data},
        ),
        "get_product": _Tool(
            function=catalog.get_product,
            description=(
                "Full detail of one product: specs, availability, price quote (promotion, PIX, "
                "installment options) and alternatives when it is not in stock."
            ),
            parameters=_object({"product_id": {"type": "integer"}}, ("product_id",)),
            inject=lambda c: {"data": c.data},
        ),
        "get_policy_sections": _Tool(
            function=policies.get_policy_sections,
            description=(
                "Text of numbered sections of the store manual (returns, shipping, payment, "
                "promotions, warranty, opening hours...). A top-level id also returns its "
                "subsections. Use the section index in the system prompt."
            ),
            parameters=_object(
                {
                    "section_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Up to 8 ids such as '4.1' or '5'.",
                    }
                },
                ("section_ids",),
            ),
            inject=lambda c: {"sections": c.policies},
        ),
        "verify_customer": _Tool(
            function=orders.verify_customer,
            description=(
                "Prove that the customer owns an order. Needs the order number and the e-mail or "
                "phone registered on that order. Required before any order data or return."
            ),
            parameters=_object(
                {
                    "order_id": order_id,
                    "contact": {"type": "string", "description": "E-mail or phone with area code."},
                },
                ("order_id", "contact"),
            ),
            inject=lambda c: {"data": c.data, "state": c.state},
        ),
        "get_order_status": _Tool(
            function=orders.get_order_status,
            description="Status, items, total, payment and tracking of a verified customer's order.",
            parameters=_object({"order_id": order_id}, ("order_id",)),
            inject=lambda c: {"data": c.data, "state": c.state, "today": c.now.date()},
        ),
        "list_my_orders": _Tool(
            function=orders.list_my_orders,
            description="List the verified customer's orders, newest first.",
            parameters=_object({}),
            inject=lambda c: {"data": c.data, "state": c.state},
        ),
        "check_return_eligibility": _Tool(
            function=returns.check_return_eligibility,
            description=(
                "Apply the return, exchange and warranty rules to a verified customer's order. "
                "Never decide eligibility yourself; call this."
            ),
            parameters=_object(
                {
                    "order_id": order_id,
                    "reason": {
                        "type": "string",
                        "enum": list(returns.REASONS),
                        "description": "regret = changed their mind; defect; preference = wants another model/color.",
                    },
                },
                ("order_id", "reason"),
            ),
            inject=lambda c: {"data": c.data, "state": c.state, "today": c.now.date()},
        ),
        "open_handoff": _Tool(
            function=handoff.open_handoff,
            description=(
                "Register a ticket for the store team (complaint, confirmed return request, "
                "defect, anything unsolved). Returns a protocol and the response deadline."
            ),
            parameters=_object(
                {
                    "category": {"type": "string", "enum": list(HANDOFF_CATEGORIES)},
                    "summary": {
                        "type": "string",
                        "description": "What happened, in one or two sentences (max 600 characters).",
                    },
                    "order_id": order_id,
                },
                ("category", "summary"),
            ),
            inject=lambda c: {
                "data": c.data,
                "state": c.state,
                "store": c.handoffs,
                "session_id": c.session_id,
                "now": c.now,
            },
            defaults={"order_id": None},
        ),
    }


def _check_value(key: str, value: Any, spec: dict[str, Any]) -> str | None:
    if not _TYPE_CHECKS[spec["type"]](value):
        return f"Argument {key!r} must be of type {spec['type']}."
    if "enum" in spec and value not in spec["enum"]:
        return f"Argument {key!r} must be one of: {', '.join(map(str, spec['enum']))}."
    return None


def _validate(args: dict[str, Any], schema: dict[str, Any]) -> str | None:
    properties = schema["properties"]
    for key in args:
        if key not in properties:
            return f"Unexpected argument {key!r}."
    for key in schema["required"]:
        if key not in args:
            return f"Missing required argument {key!r}."
    for key, value in args.items():
        problem = _check_value(key, value, properties[key])
        if problem:
            return problem
    return None


def _dump(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False)


class Toolset:
    def __init__(self, ctx: ToolContext) -> None:
        self._ctx = ctx
        self._tools = _build_tools(ctx)

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": self._tools[name].description,
                    "parameters": self._tools[name].parameters,
                },
            }
            for name in TOOL_NAMES
        ]

    def call(self, name: str, arguments_json: str) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return _dump(
                error("unknown_tool", f"Unknown tool {name!r}. Tools: {', '.join(TOOL_NAMES)}.")
            )
        try:
            args = json.loads(arguments_json) if arguments_json and arguments_json.strip() else {}
        except json.JSONDecodeError as exc:
            return _dump(error("invalid_argument", f"Arguments are not valid JSON: {exc.msg}."))
        if not isinstance(args, dict):
            return _dump(error("invalid_argument", "Arguments must be a JSON object."))

        # Models often send null for optional arguments; treat that as "not given".
        args = {key: value for key, value in args.items() if value is not None}
        problem = _validate(args, tool.parameters)
        if problem:
            return _dump(error("invalid_argument", problem))

        # Injected values win, so the model can never override the session or the data.
        kwargs = {**tool.defaults, **args, **tool.inject(self._ctx)}
        try:
            inspect.signature(tool.function).bind(**kwargs)
        except TypeError as exc:
            return _dump(error("invalid_argument", str(exc)))
        return _dump(tool.function(**kwargs))
