"""Request handling for the local web interface.

No network code lives here (see `server.py`), so every route is tested by calling `handle`.
The page is for one person on one machine: it holds one conversation at a time and answers only
requests addressed to the local host.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from emporio.config import Settings
from emporio.conversation import start_conversation
from emporio.data import StoreData, load_store_data
from emporio.db import HandoffStore, SessionStore, connect
from emporio.hours import STORE_HOURS, is_open, next_opening
from emporio.llm import ChatClient
from emporio.metrics import Prices, as_dict
from emporio.policies import PolicySection, load_policy_sections
from emporio.prompt import STORE_ADDRESS, STORE_EMAIL, STORE_PHONE, WEEKDAYS

log = logging.getLogger("emporio.web")

STATIC_DIR = Path(__file__).parent / "static"
POLICY_FILE = "políticas_da_loja.pdf"
MAX_BODY_BYTES = 16 * 1024
MAX_TEXT_CHARS = 2000
MAX_RESULT_CHARS = 4000
HIDDEN = "(oculto)"

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}
_STATIC_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_PAGE_HEADERS = (
    (
        "Content-Security-Policy",
        (
            "default-src 'self'; img-src 'self' data:; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'self'"
        ),
    ),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Cache-Control", "no-store"),
)

SUGGESTIONS = (
    {
        "kind": "data",
        "topic": "Catálogo",
        "label": "Violões até R$ 1.000",
        "text": "Quais violões vocês têm disponíveis até R$ 1000?",
    },
    {
        "kind": "data",
        "topic": "Preço e parcelas",
        "label": "Ohana CK-20 em 10x",
        "text": "Quanto custa o Ohana CK-20? Dá para parcelar em 10x?",
    },
    {
        "kind": "policy",
        "topic": "Manual da loja",
        "label": "Troca por defeito",
        "text": "Como funciona a troca por defeito?",
    },
    {
        "kind": "rules",
        "topic": "Pedido e devolução",
        "label": "Quero devolver um produto",
        "text": "Comprei um ukulele e me arrependi, quero devolver.",
    },
)
_TEST_CUSTOMER_NOTES = (
    (
        8,
        (
            "Pedido enviado, com a entrega prevista já vencida em 25/03/2026. Bom para testar "
            "status, rastreio e chamado."
        ),
    ),
    (
        7,
        (
            "Pedido entregue em 17/02/2026. Abra com --today 2026-02-19 para testar a devolução "
            "por arrependimento dentro do prazo."
        ),
    ),
)

CATEGORY_LABELS = {
    "complaint": "Reclamação",
    "return_request": "Devolução",
    "defect": "Defeito",
    "other": "Outro",
}
_AVAILABILITY = {
    "in_stock": "em estoque",
    "out_of_stock": "esgotado",
    "discontinued": "descontinuado",
    "coming_soon": "em breve",
}
_ORDER_STATUS = {
    "pending": "aguardando pagamento",
    "confirmed": "confirmado",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}
_REASONS = {"regret": "arrependimento", "defect": "defeito", "preference": "troca por preferência"}
_ERROR_SUMMARY = {
    "not_verified": "não verificado",
    "verification_locked": "tentativas esgotadas",
    "order_not_found": "pedido não encontrado",
    "product_not_found": "produto não encontrado",
}
_KIND = {
    "search_products": "data",
    "get_product": "data",
    "get_order_status": "data",
    "list_my_orders": "data",
    "get_policy_sections": "policy",
    "search_policies": "policy",
    "verify_customer": "identity",
    "check_return_eligibility": "rules",
    "open_handoff": "handoff",
}
_TITLE = {
    "search_products": "Buscou no catálogo",
    "get_product": "Abriu o produto",
    "get_order_status": "Consultou o pedido",
    "list_my_orders": "Listou os pedidos do cliente",
    "get_policy_sections": "Consultou o manual",
    "search_policies": "Buscou no manual",
    "verify_customer": "Verificou a identidade",
    "check_return_eligibility": "Aplicou as regras de devolução",
    "open_handoff": "Abriu atendimento humano",
}


@dataclass(frozen=True)
class Response:
    status: int
    content_type: str
    body: bytes
    headers: tuple[tuple[str, str], ...] = ()


def _json(status: int, payload: Any) -> Response:
    return Response(
        status,
        "application/json; charset=utf-8",
        json.dumps(payload, ensure_ascii=False).encode(),
        (("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")),
    )


def _error(status: int, message: str) -> Response:
    return _json(status, {"error": message})


# --- the trace of the tools ---------------------------------------------------------------------


def brl(value: float) -> str:
    text = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return "R$ " + (text.removesuffix(",00"))


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _day(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%d/%m")


def _parse(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _summary_search(args: dict[str, Any], result: dict[str, Any]) -> str:
    parts = [p for p in (args.get("query"), args.get("category")) if p]
    low, high = args.get("min_price_brl"), args.get("max_price_brl")
    if low is not None and high is not None:
        parts.append(f"{brl(low)} a {brl(high)}")
    elif high is not None:
        parts.append(f"até {brl(high)}")
    elif low is not None:
        parts.append(f"a partir de {brl(low)}")
    if args.get("string_type"):
        parts.append(
            {"steel": "aço", "nylon": "nylon"}.get(args["string_type"], args["string_type"])
        )
    if args.get("electroacoustic") is not None:
        parts.append("eletroacústico" if args["electroacoustic"] else "acústico")
    total = result.get("total_matches")
    if total is not None:
        parts.append("nenhum resultado" if total == 0 else _count(total, "resultado", "resultados"))
    return " · ".join(parts)


def _summary_policy(args: dict[str, Any], result: dict[str, Any]) -> str:
    sections = result.get("sections", [])
    if not sections:
        return "nenhuma seção encontrada"
    if len(sections) == 1:
        return f"item {sections[0]['id']} · {sections[0]['title']}"
    return "itens " + ", ".join(s["id"] for s in sections)


_SEARCH_METHOD = {
    "bm25": "palavras",
    "embeddings": "significado",
    "hybrid": "significado e palavras",
}


def _summary_policy_search(args: dict[str, Any], result: dict[str, Any]) -> str:
    sections = result.get("sections", [])
    if not sections:
        return "nada encontrado"
    ids = ", ".join(s["id"] for s in sections)
    found = f"item {ids}" if len(sections) == 1 else f"itens {ids}"
    method = _SEARCH_METHOD.get(result.get("method", ""))
    return f"{method} · {found}" if method else found


def _summary_verify(args: dict[str, Any], result: dict[str, Any]) -> str:
    order = f"pedido {args.get('order_id')}"
    if result.get("verified"):
        return f"{order} · confirmado ({result.get('customer_first_name', '')})"
    return f"{order} · não confirmado"


def _summary_eligibility(args: dict[str, Any], result: dict[str, Any]) -> str:
    reason = _REASONS.get(result.get("reason", ""), result.get("reason", ""))
    if result.get("eligible"):
        deadline = result.get("deadline")
        return f"{reason} · elegível" + (f" até {_day(deadline)}" if deadline else "")
    expired = result.get("reason_code") == "window_expired"
    return f"{reason} · {'prazo vencido' if expired else 'não elegível'}"


def _summary_handoff(args: dict[str, Any], result: dict[str, Any]) -> str:
    due = datetime.fromisoformat(result["due_at"])
    existing = "já existia, " if result.get("duplicate") else ""
    return f"{result['protocol']} · {existing}resposta até {due:%d/%m às %H:%M}"


_SUMMARIES: dict[str, Callable[[dict[str, Any], dict[str, Any]], str]] = {
    "search_products": _summary_search,
    "get_product": lambda a, r: (
        f"{r.get('name', '')} · {_AVAILABILITY.get(r.get('availability'), '')}"
    ),
    "get_policy_sections": _summary_policy,
    "search_policies": _summary_policy_search,
    "verify_customer": _summary_verify,
    "get_order_status": lambda a, r: (
        f"pedido {r.get('order_id')} · {_ORDER_STATUS.get(r.get('status'), '')}"
    ),
    "list_my_orders": lambda a, r: _count(len(r.get("orders", [])), "pedido", "pedidos"),
    "check_return_eligibility": _summary_eligibility,
    "open_handoff": _summary_handoff,
}


def trace_item(name: str, arguments: str, result: str) -> dict[str, Any]:
    """One tool call as the page shows it: a kind, a Portuguese title and summary, the details."""
    args = _parse(arguments)
    parsed = _parse(result)
    data = parsed if isinstance(parsed, dict) else {}
    if isinstance(args, dict) and "contact" in args:
        args = {**args, "contact": HIDDEN}

    failed = "error" in data or data.get("verified") is False
    if "error" in data:
        error = data["error"]
        summary = _ERROR_SUMMARY.get(error.get("code"), error.get("message", "erro"))
    else:
        summary = _SUMMARIES.get(name, lambda a, r: "")(
            args if isinstance(args, dict) else {}, data
        )

    truncated = len(result) > MAX_RESULT_CHARS
    return {
        "name": name,
        "kind": _KIND.get(name, "data"),
        "title": _TITLE.get(name, name),
        "summary": summary,
        "arguments": args,
        "result": result[:MAX_RESULT_CHARS] if truncated else parsed,
        "truncated": truncated,
        "ok": not failed,
    }


# --- the application ----------------------------------------------------------------------------


class WebApp:
    def __init__(
        self,
        settings: Settings,
        client: ChatClient,
        *,
        port: int,
        data: StoreData | None = None,
        policies: tuple[PolicySection, ...] | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.port = port
        self.data = data if data is not None else load_store_data(settings.data_dir)
        self.policies = (
            policies
            if policies is not None
            else load_policy_sections(settings.data_dir / POLICY_FILE)
        )
        conn = connect(settings.db_path)
        self.sessions = SessionStore(conn)
        self.handoffs = HandoffStore(conn)
        self._session_id: str | None = None
        self._history: list[dict[str, Any]] = []
        self._conversation: Any = None

    # The session is created on first use, so a server that fails to start leaves nothing behind.
    def _start_session(self) -> None:
        s = self.settings
        self._session_id = self.sessions.create_session(s.llm_model, s.today, s.now)
        self._history = []
        self._conversation = start_conversation(
            s, self.client, self.data, self.policies, self.handoffs, self._session_id
        )

    @property
    def session_id(self) -> str:
        if self._session_id is None:
            self._start_session()
        return self._session_id

    @property
    def conversation(self) -> Any:
        self.session_id  # noqa: B018  (makes sure a session exists)
        return self._conversation

    # --- routing

    def _allowed_hosts(self) -> set[str]:
        return {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    def _is_local(self, headers: Mapping[str, str]) -> bool:
        if headers.get("host", "").lower() not in self._allowed_hosts():
            return False
        origin = headers.get("origin")
        return origin is None or origin.lower() in {f"http://{h}" for h in self._allowed_hosts()}

    def handle(self, method: str, path: str, headers: Mapping[str, str], body: bytes) -> Response:
        lowered = {k.lower(): v for k, v in headers.items()}
        if not self._is_local(lowered):
            return _error(403, "Esta página só responde no próprio computador.")
        route = unquote(path.split("?", 1)[0])
        get_routes = {"/", "/loja", "/api/state", "/api/handoffs"}
        post_routes = {"/api/chat", "/api/reset"}
        if method == "GET":
            if route in get_routes:
                return self._get(route)
            if route.startswith("/static/"):
                return self._static(route.removeprefix("/static/"))
            return (
                _error(405, "Use POST.") if route in post_routes else _error(404, "Não encontrado.")
            )
        if method == "POST":
            if route in post_routes:
                return self._post(route, lowered, body)
            return (
                _error(405, "Use GET.") if route in get_routes else _error(404, "Não encontrado.")
            )
        return _error(405, "Método não permitido.")

    def _get(self, route: str) -> Response:
        if route == "/":
            return self._static("index.html")
        if route == "/loja":
            return self._static("loja.html")
        if route == "/api/state":
            return _json(200, self.state())
        return _json(200, {"tickets": self.tickets()})

    def _static(self, name: str) -> Response:
        path = STATIC_DIR / name
        if (
            not _STATIC_NAME.fullmatch(name)
            or not path.is_file()
            or path.suffix not in CONTENT_TYPES
        ):
            return _error(404, "Não encontrado.")
        headers = (
            _PAGE_HEADERS if path.suffix == ".html" else (("X-Content-Type-Options", "nosniff"),)
        )
        return Response(200, CONTENT_TYPES[path.suffix], path.read_bytes(), headers)

    def _post(self, route: str, headers: Mapping[str, str], body: bytes) -> Response:
        if len(body) > MAX_BODY_BYTES:
            return _error(413, "Mensagem grande demais.")
        if headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            return _error(415, "Envie JSON.")
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError:
            return _error(400, "JSON inválido.")
        if not isinstance(payload, dict):
            return _error(400, "Envie um objeto JSON.")
        if route == "/api/reset":
            self._start_session()
            return _json(200, {"session_id": self.session_id, "verified": None})
        return self._chat(payload)

    def _prices(self) -> Prices:
        return Prices(self.settings.price_in_per_m, self.settings.price_out_per_m)

    # --- chat

    def _chat(self, payload: dict[str, Any]) -> Response:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return _error(400, "Escreva uma mensagem.")
        text = text.strip()
        if len(text) > MAX_TEXT_CHARS:
            return _error(400, f"Use até {MAX_TEXT_CHARS} caracteres.")
        try:
            turn = self.conversation.reply(self._history, text)
        except Exception:  # shown to the person as a short message; the details go to the log
            log.exception("model call failed")
            return _error(502, "A Melô não conseguiu responder agora. Tente de novo em instantes.")
        self.sessions.append_messages(
            self.session_id, turn.new_messages, datetime.now(), turn.metrics
        )
        self._history.extend(turn.new_messages)
        return _json(
            200,
            {
                "reply": turn.reply,
                "trace": [trace_item(c.name, c.arguments, c.result) for c in turn.tool_calls],
                "metrics": as_dict(turn.metrics, self._prices()),
                "verified": self.verified(),
                "handoffs_open": len(self.handoffs.list_open()),
            },
        )

    # --- what the page shows

    def verified(self) -> dict[str, str] | None:
        customer_id = self.conversation.state.verified_customer_id
        if customer_id is None:
            return None
        customers = self.data.customers
        name = customers.loc[customers.customer_id == customer_id, "name"].iloc[0]
        return {"first_name": name.split()[0]}

    def turns(self) -> list[dict[str, Any]]:
        turns: list[dict[str, Any]] = []
        calls: dict[str, dict[str, str]] = {}
        stored = self.sessions.load_turn_metrics(self._session_id) if self._session_id else {}
        for message in self._history:
            if message["role"] == "user":
                found = stored.get(len(turns))
                turns.append(
                    {
                        "user": message["content"],
                        "reply": "",
                        "trace": [],
                        "metrics": as_dict(found, self._prices()) if found else None,
                    }
                )
                calls = {}
            elif message["role"] == "assistant":
                for call in message.get("tool_calls", []):
                    calls[call["id"]] = call["function"]
                if message.get("content") and not message.get("tool_calls"):
                    turns[-1]["reply"] = message["content"]
            elif message["role"] == "tool":
                function = calls[message["tool_call_id"]]
                turns[-1]["trace"].append(
                    trace_item(function["name"], function["arguments"], message["content"])
                )
        return turns

    def store_status(self) -> dict[str, Any]:
        now = self.settings.now
        weekday = STORE_HOURS[0]
        saturday = STORE_HOURS[5]
        base = {
            "name": "Empório da Música",
            "hours": [
                {"label": "Segunda a sexta", "value": f"{weekday[0]:%H:%M} às {weekday[1]:%H:%M}"},
                {"label": "Sábado", "value": f"{saturday[0]:%H:%M} às {saturday[1]:%H:%M}"},
                {"label": "Domingo e feriados", "value": "Fechado"},
            ],
            "address": STORE_ADDRESS,
            "phone": STORE_PHONE,
            "email": STORE_EMAIL,
        }
        if is_open(now):
            closing = STORE_HOURS[now.weekday()][1]
            return {
                **base,
                "open": True,
                "status_text": f"Aberta agora · fecha às {closing:%H:%M}",
                "next_opening": None,
            }
        opening = next_opening(now)
        return {
            **base,
            "open": False,
            "status_text": f"Fechada agora · abre {WEEKDAYS[opening.weekday()]} às {opening:%H:%M}",
            "next_opening": opening.isoformat(timespec="seconds"),
        }

    def test_customers(self) -> list[dict[str, Any]]:
        data = self.data
        found = []
        for order_id, note in _TEST_CUSTOMER_NOTES:
            order = data.orders[data.orders.order_id == order_id].iloc[0]
            customer = data.customers[data.customers.customer_id == order.customer_id].iloc[0]
            found.append(
                {
                    "name": customer["name"],
                    "order_id": order_id,
                    "email": customer["email"],
                    "phone": customer["phone"],
                    "note": note,
                }
            )
        return found

    def state(self) -> dict[str, Any]:
        settings = self.settings
        return {
            "store": self.store_status(),
            "reference": {
                "date": settings.today.isoformat(),
                "label": settings.today.strftime("%d/%m/%Y"),
                "simulated": settings.simulated,
            },
            "model": settings.llm_model,
            "session_id": self.session_id,
            "verified": self.verified(),
            "suggestions": list(SUGGESTIONS),
            "handoffs_open": len(self.handoffs.list_open()),
            "test_customers": self.test_customers(),
            "turns": self.turns(),
        }

    def tickets(self) -> list[dict[str, Any]]:
        return [
            {
                "protocol": t.protocol,
                "category": t.category,
                "category_label": CATEGORY_LABELS.get(t.category, t.category),
                "summary": t.summary,
                "order_id": t.order_id,
                "due_at": t.due_at.isoformat(timespec="seconds"),
                "created_at": t.created_at.isoformat(timespec="seconds"),
            }
            for t in self.handoffs.list_open()
        ]
