import re
from datetime import date

import pytest

from emporio.agent import AgentTurn, ToolCallRecord
from emporio.config import load_settings
from emporio.data import load_store_data
from emporio.evals.cases import CASES, EvalCase
from emporio.evals.runner import evaluate_case, gate, grounded_prices, parse_amounts, run_case
from emporio.tools import TOOL_NAMES
from tests.fakes import FakeChatClient, assistant_calls, assistant_text, tool_call

SETTINGS = load_settings({"EMPORIO_TODAY": "2026-03-25"})


def turn(reply, *calls, user="pergunta"):
    records = [ToolCallRecord(name, "{}", result) for name, result in calls]
    return AgentTurn(reply, [{"role": "user", "content": user}], records)


# --- the cases themselves ---------------------------------------------------------------------


def test_cases_are_well_formed():
    assert 30 <= len(CASES) <= 40  # 21 routing cases plus the adversarial ones (spec 16)
    ids = [c.id for c in CASES]
    assert len(set(ids)) == len(ids)
    customers = set(load_store_data(SETTINGS.data_dir).customers.customer_id)
    for case in CASES:
        assert case.messages and all(m.strip() for m in case.messages), case.id
        assert set(case.expect_tools_any) <= set(TOOL_NAMES), case.id
        assert set(case.forbid_tools) <= set(TOOL_NAMES), case.id
        assert not set(case.expect_tools_any) & set(case.forbid_tools), case.id
        assert (
            case.expect_tools_any
            or case.forbid_tools
            or case.reply_must_match_any
            or case.reply_must_not_match
        ), case.id
        for pattern in (*case.reply_must_match_any, *case.reply_must_not_match):
            re.compile(pattern)
        date.fromisoformat(case.today)
        assert case.verified_as is None or case.verified_as in customers, case.id


def test_the_cases_cover_the_main_behaviors():
    tags = {tag for case in CASES for tag in case.tags}
    assert {"catalog", "price", "returns", "orders", "privacy", "scope", "store"} <= tags


# --- price grounding --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("custa R$ 2.199,00 hoje", [("R$ 2.199,00", 2199.0)]),
        ("até R$1000", [("R$1000", 1000.0)]),
        ("R$ 1.000", [("R$ 1.000", 1000.0)]),
        ("R$ 1.000,50 ou R$ 80.", [("R$ 1.000,50", 1000.5), ("R$ 80", 80.0)]),
        ("R$ 439,2", [("R$ 439,2", 439.2)]),
        ("sem preço aqui", []),
    ],
)
def test_amounts_in_brazilian_formats_are_parsed(text, expected):
    assert parse_amounts(text) == expected


def test_a_price_from_a_tool_result_is_grounded():
    assert grounded_prices("O GD20 custa R$ 2.199,00.", ['{"price_brl": 2199.0}'], "") == []


def test_a_price_nobody_provided_is_reported():
    assert grounded_prices("Custa R$ 2.500,00.", ['{"price_brl": 2199.0}'], "") == ["R$ 2.500,00"]


def test_an_amount_the_customer_said_is_grounded():
    assert grounded_prices("Até R$ 1000, certo?", [], "violões até R$ 1000") == []


def test_matching_tolerates_half_a_cent_and_nothing_more():
    results = ['{"price_brl": 439.2}']
    assert grounded_prices("R$ 439,20", results, "") == []
    assert grounded_prices("R$ 439,25", results, "") == ["R$ 439,25"]


# --- evaluating a case ----------------------------------------------------------------------


def case(**overrides):
    base = {"id": "X", "messages": ("oi",)}
    base.update(overrides)
    return EvalCase(**base)


def test_a_matching_case_passes():
    c = case(expect_tools_any=("get_product",), reply_must_match_any=(r"2\.199",))
    result = evaluate_case(
        c, [turn("Custa R$ 2.199,00.", ("get_product", '{"price_brl": 2199.0}'))]
    )
    assert result.passed and result.failures == [] and result.tool_names == ["get_product"]


def test_each_kind_of_failure_is_reported():
    c = case(
        expect_tools_any=("get_product",),
        forbid_tools=("open_handoff",),
        reply_must_match_any=(r"vai bater",),
        reply_must_not_match=(r"secreto",),
    )
    result = evaluate_case(
        c, [turn("É secreto e custa R$ 9,99.", ("open_handoff", '{"protocol": "EMP"}'))]
    )
    text = " | ".join(result.failures)
    assert not result.passed
    assert "expected one of" in text
    assert "forbidden tool" in text and "open_handoff" in text
    assert "matches none" in text
    assert "secreto" in text
    assert "R$ 9,99" in text


def test_must_not_match_looks_at_every_reply_but_must_match_only_at_the_last():
    c = case(
        messages=("a", "b"), reply_must_match_any=(r"final",), reply_must_not_match=(r"vazou",)
    )
    ok = evaluate_case(c, [turn("primeira"), turn("resposta final")])
    assert ok.passed
    leaked = evaluate_case(c, [turn("vazou"), turn("resposta final")])
    assert not leaked.passed


def test_grounding_uses_tool_results_from_earlier_turns():
    c = case(messages=("a", "b"))
    turns = [turn("ok", ("get_product", '{"price_brl": 100.0}')), turn("Custa R$ 100,00.")]
    assert evaluate_case(c, turns).passed


# --- running a case with a scripted model -----------------------------------------------------


def test_run_case_drives_the_real_tools_with_a_scripted_model():
    client = FakeChatClient(
        [
            assistant_calls(tool_call("c1", "get_product", {"product_id": 95})),
            assistant_text("O Takamine GD20 custa R$ 2.199,00."),
        ]
    )
    c = case(
        messages=("Quanto custa o Takamine GD20?",),
        expect_tools_any=("get_product",),
        reply_must_match_any=(r"2\.199",),
    )
    result = run_case(c, client, SETTINGS)
    assert result.passed and result.tool_names == ["get_product"]
    assert "2.199,00" in result.replies[0]


def test_run_case_presets_the_verified_customer_and_the_reference_date():
    client = FakeChatClient(
        [
            assistant_calls(
                tool_call("c1", "check_return_eligibility", {"order_id": 7, "reason": "regret"})
            ),
            assistant_text("Dá para devolver, ainda está no prazo de 7 dias."),
        ]
    )
    c = case(
        messages=("Quero devolver o pedido 7.",),
        verified_as=14,
        today="2026-02-19",
        expect_tools_any=("check_return_eligibility",),
    )
    result = run_case(c, client, SETTINGS)
    assert result.passed
    system_prompt = client.calls[0][0][0]["content"]
    assert "quinta-feira, 19/02/2026" in system_prompt
    tool_message = client.calls[1][0][-1]
    assert '"eligible": true' in tool_message["content"]


def test_run_case_keeps_a_multi_turn_conversation_and_stays_in_memory(tmp_path):
    settings = load_settings({"EMPORIO_DB_PATH": str(tmp_path / "never.db")})
    client = FakeChatClient(
        [assistant_text("Qual o número do pedido?"), assistant_text("Anotado.")]
    )
    c = case(messages=("Quero reclamar.", "É o pedido 7."))
    result = run_case(c, client, settings)
    assert len(result.replies) == 2
    assert [m["role"] for m in client.calls[1][0]] == ["system", "user", "assistant", "user"]
    assert not settings.db_path.exists()


# --- the release gate ---------------------------------------------------------------------------


def _report(*outcomes):
    return {
        "passed": sum(ok for _, ok in outcomes),
        "total": len(outcomes),
        "cases": [{"id": case_id, "passed": ok} for case_id, ok in outcomes],
    }


def test_the_gate_is_silent_when_no_check_is_on():
    assert gate(_report(("E01", False)), None, None) == []


def test_the_gate_blocks_a_pass_rate_under_the_floor():
    problems = gate(_report(("E01", True), ("E02", False)), None, 0.9)
    assert problems == ["pass rate 50% is under the floor of 90%"]
    assert gate(_report(("E01", True), ("E02", True)), None, 0.9) == []


def test_the_gate_blocks_a_case_that_passed_in_the_baseline_and_fails_now():
    baseline = _report(("E01", True), ("E02", False))
    problems = gate(_report(("E01", False), ("E02", False)), baseline, None)
    assert problems == ["regression: E01 passed in the baseline and fails now"]


def test_a_case_that_already_failed_in_the_baseline_is_not_a_regression():
    baseline = _report(("E01", True), ("E02", False))
    assert gate(_report(("E01", True), ("E02", False)), baseline, None) == []


def test_the_gate_reports_a_run_with_no_cases_when_a_floor_is_set():
    assert gate(_report(), None, 0.5) == ["pass rate 0% is under the floor of 50%"]
