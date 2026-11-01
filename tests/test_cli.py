import socket
from datetime import date, datetime

import pytest

from emporio import cli
from emporio.agent import AgentTurn
from emporio.db import HandoffStore, SessionStore, UnknownSessionError, connect
from tests.fakes import FakeChatClient, assistant_calls, assistant_text, tool_call

NOW = datetime(2026, 3, 25, 10, 0)


@pytest.fixture
def env(tmp_path):
    return {
        "EMPORIO_DB_PATH": str(tmp_path / "var" / "e.db"),
        "EMPORIO_TODAY": "2026-03-25",
        "LLM_API_KEY": "test-key",
        "LLM_MODEL": "test/model",
    }


def run(argv, env, *, client=None, inputs=()):
    """Run the CLI with injected I/O; returns (exit code, everything written to stdout)."""
    written = []
    feed = iter(inputs)

    def read(_prompt):
        try:
            return next(feed)
        except StopIteration:
            raise EOFError from None

    code = cli.main(
        argv, env=env, client_factory=lambda settings: client, read=read, write=written.append
    )
    return code, "\n".join(written)


def stub_turn(text, reply):
    return AgentTurn(
        reply,
        [{"role": "user", "content": text}, {"role": "assistant", "content": reply}],
        [],
    )


def new_store():
    conn = connect(":memory:")
    store = SessionStore(conn)
    return store, store.create_session("test/model", date(2026, 3, 25), NOW)


# --- run_chat -------------------------------------------------------------------------------


@pytest.mark.parametrize("word", ["sair", "exit", "quit", "SAIR"])
def test_chat_persists_turns_ignores_blank_lines_and_stops_on_exit_words(word):
    store, sid = new_store()
    calls = []

    def reply(history, text):
        calls.append((list(history), text))
        return stub_turn(text, "Oi!")

    out = []
    inputs = iter(["", "   ", "olá", word, "nunca lido"])
    cli.run_chat(reply, store, sid, lambda _p: next(inputs), out.append)

    assert calls == [([], "olá")]
    assert store.load_messages(sid) == stub_turn("olá", "Oi!").new_messages
    text = "\n".join(out)
    assert "Melô: Oi!" in text and sid in text and f"--resume {sid}" in text


@pytest.mark.parametrize("interruption", [EOFError, KeyboardInterrupt])
def test_chat_ends_on_eof_and_ctrl_c(interruption):
    store, sid = new_store()
    out = []

    def read(_prompt):
        raise interruption

    cli.run_chat(lambda h, t: stub_turn(t, "x"), store, sid, read, out.append)
    assert sid in "\n".join(out)


def test_each_turn_receives_the_conversation_so_far():
    store, sid = new_store()
    seen = []

    def reply(history, text):
        seen.append(list(history))
        return stub_turn(text, f"re: {text}")

    inputs = iter(["um", "dois", "sair"])
    cli.run_chat(reply, store, sid, lambda _p: next(inputs), lambda _t: None)
    assert seen[0] == []
    assert seen[1] == stub_turn("um", "re: um").new_messages
    assert len(store.load_messages(sid)) == 4


# --- export ---------------------------------------------------------------------------------


def test_export_markdown_matches_the_expected_transcript():
    store, sid = new_store()
    store.append_messages(
        sid,
        [
            {"role": "user", "content": "Quanto custa o Takamine GD20?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    tool_call("c1", "get_product", {"product_id": 95}),
                    tool_call("c2", "get_policy_sections", {"section_ids": ["3"]}),
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": '{"price_brl": 2199.0}'},
            {"role": "tool", "tool_call_id": "c2", "content": '{"sections": []}'},
            {"role": "assistant", "content": "Custa R$ 2.199,00. 🎸"},
        ],
        NOW,
    )
    assert cli.export_markdown(store, sid) == (
        f"# Conversation {sid}\n"
        "\n"
        "- Model: test/model\n"
        "- Reference date: 2026-03-25\n"
        "- Created: 2026-03-25 10:00\n"
        "\n"
        "**Cliente:** Quanto custa o Takamine GD20?\n"
        "\n"
        '> tool: get_product({"product_id": 95})\n'
        '> tool: get_policy_sections({"section_ids": ["3"]})\n'
        '> result: {"price_brl": 2199.0}\n'
        '> result: {"sections": []}\n'
        "\n"
        "**Melô:** Custa R$ 2.199,00. 🎸\n"
    )


def test_export_of_an_empty_session_is_only_the_header():
    store, sid = new_store()
    text = cli.export_markdown(store, sid)
    assert text.startswith(f"# Conversation {sid}") and "**" not in text


def test_long_tool_results_are_truncated_in_the_export():
    store, sid = new_store()
    store.append_message(sid, {"role": "tool", "tool_call_id": "c", "content": "x" * 5000}, NOW)
    line = next(ln for ln in cli.export_markdown(store, sid).splitlines() if "result:" in ln)
    assert line == "> result: " + "x" * 300 + "…"


def test_export_of_an_unknown_session_raises():
    store, _ = new_store()
    with pytest.raises(UnknownSessionError):
        cli.export_markdown(store, "nope")


# --- commands -------------------------------------------------------------------------------


def seed(env):
    conn = connect(env["EMPORIO_DB_PATH"])
    sessions = SessionStore(conn)
    sid = sessions.create_session("test/model", date(2026, 3, 25), NOW)
    sessions.append_messages(
        sid,
        [
            {"role": "user", "content": "Quais violões vocês têm?"},
            {"role": "assistant", "content": "Temos!"},
        ],
        NOW,
    )
    HandoffStore(conn).create(
        category="complaint",
        summary="Violão chegou riscado.",
        customer_id=3,
        order_id=1,
        session_id=sid,
        created_at=NOW,
        due_at=datetime(2026, 3, 27, 16, 0),
    )
    conn.close()
    return sid


def test_sessions_and_handoffs_listings(env):
    sid = seed(env)
    code, out = run(["sessions"], env)
    assert (
        code == 0 and sid in out and "Quais violões vocês têm?" in out and "2026-03-25 10:00" in out
    )
    code, out = run(["handoffs"], env)
    assert code == 0 and "EMP-20260325-0001" in out and "complaint" in out
    assert "2026-03-27 16:00" in out and "Violão chegou riscado." in out


def test_empty_listings_say_so(env):
    assert "No sessions" in run(["sessions"], env)[1]
    assert "No open" in run(["handoffs"], env)[1]


def test_export_command_writes_stdout_or_a_file(env, tmp_path):
    sid = seed(env)
    code, out = run(["export", sid], env)
    assert code == 0 and "**Cliente:** Quais violões vocês têm?" in out
    target = tmp_path / "out" / "t.md"
    code, _ = run(["export", sid, "-o", str(target)], env)
    assert code == 0 and "**Melô:** Temos!" in target.read_text(encoding="utf-8")


def test_data_report_groups_issues_by_kind(env):
    code, out = run(["data-report"], env)
    assert code == 0
    assert "order_total_mismatch (2)" in out and "order 3" in out and "order 20" in out
    assert "duplicate_email" in out and "customers 11,43" in out


# --- chat, resume, replay ---------------------------------------------------------------------


def test_no_subcommand_starts_a_chat_and_persists_the_conversation(env):
    client = FakeChatClient([assistant_text("Oi! Como posso ajudar?")])
    code, out = run([], env, client=client, inputs=["oi", "sair"])
    assert code == 0
    assert "Melô" in out and "Oi! Como posso ajudar?" in out
    system, user = client.calls[0][0][0], client.calls[0][0][-1]
    assert system["role"] == "system" and "quarta-feira, 25/03/2026" in system["content"]
    assert user == {"role": "user", "content": "oi"}
    info = SessionStore(connect(env["EMPORIO_DB_PATH"])).list_sessions()[0]
    assert (info.message_count, info.model, info.reference_date) == (
        2,
        "test/model",
        date(2026, 3, 25),
    )


def test_chat_runs_the_tools_through_the_real_toolset(env):
    client = FakeChatClient(
        [
            assistant_calls(tool_call("c1", "get_product", {"product_id": 95})),
            assistant_text("O Takamine GD20 custa R$ 2.199,00."),
        ]
    )
    code, out = run(["chat"], env, client=client, inputs=["quanto custa o gd20?", "sair"])
    assert code == 0 and "2.199,00" in out
    tool_message = client.calls[1][0][-1]
    assert tool_message["role"] == "tool" and '"price_brl": 2199.0' in tool_message["content"]


def test_resume_loads_the_history_and_warns_that_verification_restarts(env):
    sid = seed(env)
    client = FakeChatClient([assistant_text("Claro!")])
    code, out = run(["chat", "--resume", sid], env, client=client, inputs=["e o preço?", "sair"])
    assert code == 0
    assert "confirme o pedido de novo" in out and sid in out
    sent = client.calls[0][0]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[1]["content"] == "Quais violões vocês têm?"
    assert len(SessionStore(connect(env["EMPORIO_DB_PATH"])).load_messages(sid)) == 4


def test_verbose_prints_tool_calls_to_stderr(env, capsys):
    client = FakeChatClient(
        [assistant_calls(tool_call("c1", "get_product", {"product_id": 95})), assistant_text("ok")]
    )
    run(["chat", "--verbose"], env, client=client, inputs=["x", "sair"])
    assert "[tool] get_product" in capsys.readouterr().err


def test_today_flag_overrides_the_environment(env):
    client = FakeChatClient([assistant_text("ok")])
    run(["chat", "--today", "2026-02-19"], env, client=client, inputs=["x", "sair"])
    assert "quinta-feira, 19/02/2026" in client.calls[0][0][0]["content"]


def test_replay_writes_a_transcript_of_the_scripted_conversation(env, tmp_path):
    script = tmp_path / "script.txt"
    script.write_text("# comment\n\nQuanto custa o Takamine GD20?\nObrigado!\n", encoding="utf-8")
    client = FakeChatClient(
        [
            assistant_calls(tool_call("c1", "get_product", {"product_id": 95})),
            assistant_text("Custa R$ 2.199,00."),
            assistant_text("Por nada! 🎸"),
        ]
    )
    target = tmp_path / "samples" / "t.md"
    code, out = run(["replay", str(script), "-o", str(target)], env, client=client)
    assert code == 0 and str(target) in out
    text = target.read_text(encoding="utf-8")
    assert text.count("**Cliente:**") == 2 and "> tool: get_product" in text
    assert "- Model: test/model" in text and "- Reference date: 2026-03-25" in text


def test_replay_to_stdout(env, tmp_path):
    script = tmp_path / "s.txt"
    script.write_text("oi\n", encoding="utf-8")
    code, out = run(["replay", str(script)], env, client=FakeChatClient([assistant_text("Olá!")]))
    assert code == 0 and "**Melô:** Olá!" in out


# --- failures ---------------------------------------------------------------------------------


def test_a_script_without_messages_is_rejected(env, tmp_path, capsys):
    script = tmp_path / "s.txt"
    script.write_text("# only comments\n\n", encoding="utf-8")
    code, _ = run(["replay", str(script)], env, client=FakeChatClient([]))
    assert code == 2 and "script has no messages" in capsys.readouterr().err


def test_a_missing_script_is_rejected(env, tmp_path, capsys):
    code, _ = run(["replay", str(tmp_path / "nope.txt")], env, client=FakeChatClient([]))
    assert code == 2 and "not found" in capsys.readouterr().err


def test_unknown_session_exits_with_code_2(env, capsys):
    for argv in (["chat", "--resume", "nope"], ["export", "nope"]):
        code, _ = run(argv, env, client=FakeChatClient([]))
        assert code == 2
    assert "Unknown session: nope" in capsys.readouterr().err


def test_invalid_today_exits_with_code_2(env, capsys):
    code, _ = run(["chat", "--today", "25/03"], env, client=FakeChatClient([]))
    assert code == 2 and "EMPORIO_TODAY" in capsys.readouterr().err


def test_missing_api_key_exits_with_code_1(env, capsys):
    env = {k: v for k, v in env.items() if k != "LLM_API_KEY"}
    written = []
    code = cli.main(["chat"], env=env, read=lambda _p: "sair", write=written.append)
    assert code == 1
    assert "Set LLM_API_KEY (see .env.example)" in capsys.readouterr().err
    assert not SessionStore(connect(env["EMPORIO_DB_PATH"])).list_sessions()


def test_malformed_tool_arguments_are_shown_as_the_model_sent_them():
    store, sid = new_store()
    store.append_message(
        sid,
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "c", "type": "function", "function": {"name": "f", "arguments": "{oops"}}
            ],
        },
        NOW,
    )
    assert "> tool: f({oops)" in cli.export_markdown(store, sid)


# --- web ------------------------------------------------------------------------------------


def test_web_without_an_api_key_exits_with_code_1_and_creates_no_session(env, capsys):
    env = {k: v for k, v in env.items() if k != "LLM_API_KEY"}
    code = cli.main(["web", "--no-browser"], env=env, write=lambda _t: None)
    assert code == 1
    assert "Set LLM_API_KEY (see .env.example)" in capsys.readouterr().err
    assert SessionStore(connect(env["EMPORIO_DB_PATH"])).list_sessions() == []


def test_web_on_a_busy_port_exits_with_code_1_and_creates_no_session(env, capsys):
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        code = cli.main(
            ["web", "--port", str(port), "--no-browser"],
            env=env,
            client_factory=lambda settings: FakeChatClient([]),
            write=lambda _t: None,
        )
    assert code == 1
    assert f"127.0.0.1:{port}" in capsys.readouterr().err
    assert SessionStore(connect(env["EMPORIO_DB_PATH"])).list_sessions() == []


def test_web_is_a_known_command_with_its_options():
    args = cli.build_parser().parse_args(
        ["web", "--port", "9000", "--today", "2026-02-19", "--no-browser"]
    )
    assert (args.command, args.port, args.today, args.no_browser) == (
        "web",
        9000,
        "2026-02-19",
        True,
    )
    assert cli.build_parser().parse_args(["web"]).port == 8765
