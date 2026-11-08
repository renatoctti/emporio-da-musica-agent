import pytest

from emporio.evals.judge import (
    DEFAULT_LABELS,
    Verdict,
    agreement,
    build_messages,
    judge_reply,
    load_labels,
    parse_verdict,
)
from tests.fakes import FakeChatClient, assistant_text


def test_a_verdict_line_is_parsed_with_its_reason():
    assert parse_verdict("VERDICT: PASS\nShort and friendly.") == Verdict(
        True, "Short and friendly."
    )
    assert parse_verdict("verdict: fail - uses a heading") == Verdict(False, "uses a heading")


@pytest.mark.parametrize("text", [None, "", "The reply looks fine to me.", "VERDICT: MAYBE"])
def test_an_answer_without_a_verdict_is_not_parsed(text):
    assert parse_verdict(text) is None


def test_the_judge_sees_the_rubric_the_customer_message_and_the_reply():
    system, user = build_messages("Oi", "Olá! Tudo bem?")
    assert system["role"] == "system" and "VERDICT: PASS" in system["content"]
    assert "Oi" in user["content"] and "Olá! Tudo bem?" in user["content"]


def test_judge_reply_returns_the_verdict_and_asks_without_tools():
    client = FakeChatClient([assistant_text("VERDICT: FAIL\nIt is in Portuguese.")])
    verdict = judge_reply(client, "Hi", "Olá")
    assert verdict == Verdict(False, "It is in Portuguese.")
    assert client.calls[0][1] == []


def test_judge_reply_rejects_an_answer_in_the_wrong_format():
    client = FakeChatClient([assistant_text("Looks good!")])
    with pytest.raises(ValueError, match="PASS or FAIL"):
        judge_reply(client, "Hi", "Hello")


def test_agreement_counts_both_kinds_of_mistake_and_corrects_for_chance():
    pairs = [(True, True), (True, False), (False, False), (False, False)]
    stats = agreement(pairs)
    assert stats["n"] == 4 and stats["accuracy"] == 0.75
    assert stats["false_fail"] == 1 and stats["false_pass"] == 0
    assert stats["kappa"] == pytest.approx(0.5)


def test_a_judge_that_always_passes_gets_no_credit_beyond_chance():
    pairs = [(True, True)] * 9 + [(False, True)]
    assert agreement(pairs)["accuracy"] == 0.9
    assert agreement(pairs)["kappa"] == 0.0


def test_perfect_agreement_is_kappa_one_even_when_every_label_is_the_same():
    assert agreement([(True, True), (True, True)])["kappa"] == 1.0
    assert agreement([(True, True), (False, False)])["kappa"] == 1.0


def test_agreement_needs_at_least_one_labeled_reply():
    with pytest.raises(ValueError):
        agreement([])


def test_load_labels_skips_unlabeled_rows_and_rejects_a_bad_label(tmp_path):
    path = tmp_path / "labels.csv"
    path.write_text(
        "id,customer_message,reply,human_label\n"
        'L01,Oi,"Olá, tudo bem?",pass\n'
        "L02,Oi,Prezado cliente,\n"
        "L03,Hi,Olá,FAIL\n",
        encoding="utf-8",
    )
    rows = load_labels(path)
    assert [(r.row_id, r.human_pass) for r in rows] == [("L01", True), ("L03", False)]
    path.write_text("id,customer_message,reply,human_label\nL04,Oi,Olá,talvez\n", encoding="utf-8")
    with pytest.raises(ValueError, match="L04"):
        load_labels(path)


def test_the_shipped_labels_file_has_the_columns_the_loader_reads():
    header = DEFAULT_LABELS.read_text(encoding="utf-8-sig").splitlines()[0]
    assert header.split(",")[:4] == ["id", "customer_message", "reply", "human_label"]
