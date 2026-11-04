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


README_HEADINGS = [
    "## Overview",
    "## Quick start",
    "## Configuration",
    "## Commands",
    "## Architecture",
    "## Decisions and why",
    "## Data handling",
    "## Prompt strategy",
    "## Evaluation",
    "## Assumptions",
    "## Limitations and next steps",
    "## AI coding assistants",
    "## Sample conversations",
    "## Repository layout",
]


def readme():
    return (ROOT / "README.md").read_text(encoding="utf-8")


def section(title):
    text = readme()
    start = text.index(title)
    following = [text.index(h, start + 1) for h in README_HEADINGS if text.find(h, start + 1) > 0]
    return text[start : min(following)] if following else text[start:]


def test_readme_has_every_required_section_in_order():
    text = readme()
    positions = [text.find(heading) for heading in README_HEADINGS]
    assert all(p >= 0 for p in positions), [h for h, p in zip(README_HEADINGS, positions) if p < 0]
    assert positions == sorted(positions)


def test_readme_quick_start_is_runnable():
    quick_start = section("## Quick start")
    for needle in ('pip install -e ".[dev]"', "LLM_API_KEY", "python -m venv", "pytest"):
        assert needle in quick_start, needle


def test_readme_lists_every_assumption():
    assumptions = section("## Assumptions")
    for n in range(1, 14):
        assert re.search(rf"\bA{n}\b", assumptions), f"A{n}"


def test_readme_reports_the_evaluation_of_two_models_honestly():
    evaluation = section("## Evaluation")
    assert "claude-haiku-5.5" in evaluation and "qwen" in evaluation
    assert "21/21" in evaluation and "20/21" in evaluation
    assert "18/21" in evaluation, "the first run must be reported"
    assert "held-out" in evaluation


def test_readme_states_the_main_limits_plainly():
    limits = section("## Limitations and next steps").lower()
    for needle in ("shipping", "holiday", "lexical", "unencrypted", "simulated"):
        assert needle in limits, needle


def test_readme_explains_how_the_assistant_was_used():
    usage = section("## AI coding assistants")
    assert "Claude Code" in usage and ".specs" in usage
    assert "test-first" in usage


def test_every_sample_is_linked_from_the_readme():
    block = section("## Sample conversations")
    for name in NAMES:
        assert f"samples/{name}.md" in block


def test_readme_documents_the_web_interface_with_screenshots():
    text = readme()
    assert "emporio web" in text and "### Web interface" in text
    for image in ("docs/web-interface-light.jpg", "docs/web-interface-dark.jpg"):
        assert image in text, image
        assert (ROOT / image).stat().st_size > 10_000, image
    limits = section("## Limitations and next steps").lower()
    assert "web page" in limits and "firefox" in limits
