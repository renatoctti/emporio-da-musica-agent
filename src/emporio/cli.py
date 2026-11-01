"""Command-line interface: chat, resume, listings, transcripts and scripted replays."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from emporio.agent import AgentTurn
from emporio.config import ConfigError, Settings, load_settings
from emporio.conversation import start_conversation
from emporio.data import load_store_data
from emporio.db import HandoffStore, SessionStore, UnknownSessionError, connect
from emporio.llm import ChatClient, MissingApiKeyError, OpenAIChatClient
from emporio.policies import load_policy_sections

COMMANDS = ("chat", "sessions", "handoffs", "export", "replay", "data-report")
EXIT_WORDS = frozenset({"sair", "exit", "quit"})
POLICY_FILE = "políticas_da_loja.pdf"
RESULT_PREVIEW_CHARS = 300
GREETING = "Oi! Eu sou a Melô, assistente virtual da Empório da Música. Como posso ajudar?"
RESUME_NOTICE = (
    "Para sua segurança, confirme o pedido de novo se precisar de dados dele: "
    "a verificação não é restaurada."
)

Reply = Callable[[list[dict[str, Any]], str], AgentTurn]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emporio", description="Melô, the virtual assistant of Empório da Música."
    )
    commands = parser.add_subparsers(dest="command")

    chat = commands.add_parser("chat", help="talk to Melô (the default command)")
    chat.add_argument("--resume", metavar="SESSION_ID", help="continue a stored conversation")
    chat.add_argument("--today", metavar="YYYY-MM-DD", help="pretend today is this date")
    chat.add_argument("--verbose", action="store_true", help="print tool calls to stderr")

    commands.add_parser("sessions", help="list stored conversations")
    commands.add_parser("handoffs", help="list open handoff tickets")
    commands.add_parser("data-report", help="list the data issues found in the CSV files")

    export = commands.add_parser("export", help="print a conversation as Markdown")
    export.add_argument("session_id")
    export.add_argument("-o", "--output", metavar="FILE")

    replay = commands.add_parser("replay", help="run a script of customer messages")
    replay.add_argument("script", help="text file, one customer message per line")
    replay.add_argument("--today", metavar="YYYY-MM-DD", help="pretend today is this date")
    replay.add_argument("-o", "--output", metavar="FILE")
    return parser


# --- transcript -----------------------------------------------------------------------------


def _compact_arguments(arguments: str) -> str:
    try:
        return json.dumps(json.loads(arguments), ensure_ascii=False)
    except json.JSONDecodeError:
        return arguments  # shown as the model sent it


def _preview(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= RESULT_PREVIEW_CHARS else text[:RESULT_PREVIEW_CHARS] + "…"


def export_markdown(store: SessionStore, session_id: str) -> str:
    info = store.get_session(session_id)
    reference = info.reference_date.isoformat() if info.reference_date else "system clock"
    lines = [
        f"# Conversation {info.id}",
        "",
        f"- Model: {info.model}",
        f"- Reference date: {reference}",
        f"- Created: {info.created_at:%Y-%m-%d %H:%M}",
    ]
    previous_was_quote = False
    for message in store.load_messages(session_id):
        entries: list[tuple[bool, str]] = []  # (is_quote, text)
        if message["role"] == "user":
            entries.append((False, f"**Cliente:** {message['content']}"))
        elif message["role"] == "assistant":
            if message.get("content"):
                entries.append((False, f"**Melô:** {message['content']}"))
            for call in message.get("tool_calls", []):
                function = call["function"]
                arguments = _compact_arguments(function["arguments"])
                entries.append((True, f"> tool: {function['name']}({arguments})"))
        elif message["role"] == "tool":
            entries.append((True, f"> result: {_preview(message['content'])}"))
        for is_quote, text in entries:
            if not (is_quote and previous_was_quote):
                lines.append("")
            lines.append(text)
            previous_was_quote = is_quote
    return "\n".join(lines) + "\n"


# --- chat loop ------------------------------------------------------------------------------


def run_chat(
    reply: Reply,
    store: SessionStore,
    session_id: str,
    read: Callable[[str], str],
    write: Callable[[str], None],
) -> None:
    history = store.load_messages(session_id)
    while True:
        try:
            line = read("Você: ")
        except (EOFError, KeyboardInterrupt):
            break
        text = line.strip()
        if not text:
            continue
        if text.lower() in EXIT_WORDS:
            break
        turn = reply(history, text)
        store.append_messages(session_id, turn.new_messages, datetime.now())
        history.extend(turn.new_messages)
        write(f"Melô: {turn.reply}")
    write(f"Conversa {session_id} salva. Para retomar: emporio chat --resume {session_id}")


def _build_reply(
    settings: Settings,
    client: ChatClient,
    handoffs: HandoffStore,
    session_id: str,
    verbose: bool,
) -> Reply:
    data = load_store_data(settings.data_dir)
    policies = load_policy_sections(settings.data_dir / POLICY_FILE)
    conversation = start_conversation(settings, client, data, policies, handoffs, session_id)

    def reply(history: list[dict[str, Any]], text: str) -> AgentTurn:
        turn = conversation.reply(history, text)
        if verbose:
            for call in turn.tool_calls:
                print(
                    f"[tool] {call.name}({call.arguments}) -> {call.result[:RESULT_PREVIEW_CHARS]}",
                    file=sys.stderr,
                )
        return turn

    return reply


# --- commands -------------------------------------------------------------------------------


def _cmd_chat(
    args: argparse.Namespace,
    settings: Settings,
    client_factory: Callable[[Settings], ChatClient],
    read: Callable[[str], str],
    write: Callable[[str], None],
) -> int:
    client = client_factory(settings)  # first, so a missing key leaves no empty session behind
    conn = connect(settings.db_path)
    sessions = SessionStore(conn)
    if args.resume:
        sessions.load_messages(args.resume)  # raises UnknownSessionError before anything else
        session_id = args.resume
        write(f"Retomando a conversa {session_id}. {RESUME_NOTICE}")
    else:
        session_id = sessions.create_session(settings.llm_model, settings.today, settings.now)
        write(f"Melô: {GREETING}")
    reply = _build_reply(settings, client, HandoffStore(conn), session_id, args.verbose)
    run_chat(reply, sessions, session_id, read, write)
    return 0


def _cmd_replay(
    args: argparse.Namespace,
    settings: Settings,
    client_factory: Callable[[Settings], ChatClient],
    write: Callable[[str], None],
) -> int:
    script = Path(args.script)
    if not script.is_file():
        print(f"Script not found: {script}", file=sys.stderr)
        return 2
    lines = (line.strip() for line in script.read_text(encoding="utf-8").splitlines())
    messages = [line for line in lines if line and not line.startswith("#")]
    if not messages:
        print("script has no messages", file=sys.stderr)
        return 2

    client = client_factory(settings)
    conn = connect(settings.db_path)
    sessions = SessionStore(conn)
    session_id = sessions.create_session(settings.llm_model, settings.today, settings.now)
    reply = _build_reply(settings, client, HandoffStore(conn), session_id, verbose=False)
    history: list[dict[str, Any]] = []
    for text in messages:
        turn = reply(history, text)
        sessions.append_messages(session_id, turn.new_messages, datetime.now())
        history.extend(turn.new_messages)

    return _write_transcript(export_markdown(sessions, session_id), args.output, write)


def _write_transcript(markdown: str, output: str | None, write: Callable[[str], None]) -> int:
    if output is None:
        write(markdown.rstrip("\n"))
        return 0
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(markdown, encoding="utf-8")
    write(f"Transcript written to {target}")
    return 0


def _cmd_sessions(settings: Settings, write: Callable[[str], None]) -> int:
    infos = SessionStore(connect(settings.db_path)).list_sessions()
    if not infos:
        write("No sessions yet.")
        return 0
    write(f"{'ID':<10}{'CREATED':<18}{'MSGS':>5}  FIRST MESSAGE")
    for info in infos:
        first = (info.first_user_message or "")[:50]
        write(f"{info.id:<10}{info.created_at:%Y-%m-%d %H:%M}  {info.message_count:>5}  {first}")
    return 0


def _cmd_handoffs(settings: Settings, write: Callable[[str], None]) -> int:
    tickets = HandoffStore(connect(settings.db_path)).list_open()
    if not tickets:
        write("No open handoff tickets.")
        return 0
    write(f"{'PROTOCOL':<19}{'CATEGORY':<16}{'DUE':<18}{'ORDER':<7}SUMMARY")
    for ticket in tickets:
        order = str(ticket.order_id) if ticket.order_id is not None else "-"
        write(
            f"{ticket.protocol:<19}{ticket.category:<16}{ticket.due_at:%Y-%m-%d %H:%M}  "
            f"{order:<7}{ticket.summary[:60]}"
        )
    return 0


def _cmd_export(args: argparse.Namespace, settings: Settings, write: Callable[[str], None]) -> int:
    markdown = export_markdown(SessionStore(connect(settings.db_path)), args.session_id)
    return _write_transcript(markdown, args.output, write)


def _cmd_data_report(settings: Settings, write: Callable[[str], None]) -> int:
    by_kind = defaultdict(list)
    for issue in load_store_data(settings.data_dir).issues:
        by_kind[issue.kind].append(issue)
    for kind in sorted(by_kind):
        write(f"{kind} ({len(by_kind[kind])})")
        for issue in by_kind[kind]:
            write(f"  {issue.subject}: {issue.detail}")
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    client_factory: Callable[[Settings], ChatClient] = OpenAIChatClient,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or (argv[0] not in COMMANDS and argv[0] not in ("-h", "--help")):
        argv = ["chat", *argv]  # `emporio` alone, or `emporio --resume ID`, means chat
    args = build_parser().parse_args(argv)

    if env is None:
        load_dotenv()
        env = os.environ
    overrides = {"EMPORIO_TODAY": args.today} if getattr(args, "today", None) else {}
    try:
        settings = load_settings({**env, **overrides})
        if args.command == "chat":
            return _cmd_chat(args, settings, client_factory, read, write)
        if args.command == "replay":
            return _cmd_replay(args, settings, client_factory, write)
        if args.command == "sessions":
            return _cmd_sessions(settings, write)
        if args.command == "handoffs":
            return _cmd_handoffs(settings, write)
        if args.command == "export":
            return _cmd_export(args, settings, write)
        return _cmd_data_report(settings, write)
    except MissingApiKeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except UnknownSessionError as exc:
        print(f"Unknown session: {exc.args[0]}", file=sys.stderr)
        return 2
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
