import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
NAMES = [
    "01-catalog",
    "02-price-installments",
    "03-order-status",
    "04-return",
    "05-out-of-scope-es",
]
# Names that must never appear in the public documentation of this repository.
HIDDEN = re.compile(r"isabella|mattpocock|ponytail|spec-harness|spec-orchestrator", re.IGNORECASE)


def script_lines(name):
    return (SAMPLES / "scripts" / f"{name}.txt").read_text(encoding="utf-8").splitlines()


def transcript(name):
    return (SAMPLES / f"{name}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", NAMES)
def test_every_script_has_a_reference_date_and_customer_lines(name):
    lines = script_lines(name)
    assert re.fullmatch(r"# Reference date: \d{4}-\d{2}-\d{2}", lines[0])
    messages = [ln for ln in lines if ln.strip() and not ln.startswith("#")]
    assert messages


@pytest.mark.parametrize("name", NAMES)
def test_every_transcript_has_its_header_and_both_speakers(name):
    text = transcript(name)
    reference = script_lines(name)[0].removeprefix("# Reference date: ")
    assert text.startswith("# Conversation ")
    assert "- Model: " in text and f"- Reference date: {reference}" in text
    assert text.count("**Cliente:**") == len(
        [ln for ln in script_lines(name) if ln.strip() and not ln.startswith("#")]
    )
    assert "**Melô:**" in text


def test_the_return_sample_shows_the_whole_flow():
    text = transcript("04-return")
    for tool in ("verify_customer", "check_return_eligibility", "open_handoff"):
        assert f"> tool: {tool}(" in text
    assert re.search(r"EMP-\d{8}-\d{4}", text)


def test_the_price_sample_shows_the_installment_limit_from_the_tool():
    text = transcript("02-price-installments")
    assert "> tool: get_product(" in text and "5x" in text


def test_the_out_of_scope_sample_answers_in_the_customers_language_without_tools():
    text = transcript("05-out-of-scope-es")
    first_reply = text.split("**Melô:**")[1].split("**Cliente:**")[0]
    assert "instrumentos" in first_reply
    assert re.search(r"[¡¿ñ]|vendemos", first_reply), "the reply is not in Spanish"
    assert " não " not in first_reply.lower()
    assert "> tool:" not in first_reply


def test_no_documentation_names_the_tools_used_to_plan_the_work():
    documents = [ROOT / "README.md", ROOT / "PROJECT_MAP.md", *SAMPLES.glob("*.md")]
    documents += (ROOT / ".specs").rglob("*.md")
    for path in documents:
        assert not HIDDEN.search(path.read_text(encoding="utf-8")), path
