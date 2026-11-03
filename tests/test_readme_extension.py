"""Spec 21: the README matches what the repository does and the numbers in the JSON reports."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
RESULTS = ROOT / "evals" / "results"


def test_the_readme_documents_the_new_commands_and_settings():
    needles = (
        "emporio stats",
        "emporio mcp",
        "python -m emporio.evals.retrieval",
        "--tag adversarial",
        "docker run",
        "EMBEDDING_MODEL",
        "EMPORIO_EMBEDDINGS",
        "LLM_PRICE_IN_PER_M",
        "Modo dev",
    )
    for needle in needles:
        assert needle in README, needle


def test_the_counts_are_current_and_no_stale_count_remains():
    lowered = README.lower()
    assert "nine tools" in lowered or "nine fixed tools" in lowered
    for stale in (
        "eight tools",
        "eight fixed tools",
        "about 370 tests",
        "11 specs",
        "21 scenarios",
    ):
        assert stale not in lowered, stale
    assert "20 specs" in lowered and "33 scenarios" in lowered


def test_the_retrieval_numbers_come_from_the_report():
    report = json.loads((RESULTS / "retrieval.json").read_text(encoding="utf-8"))
    assert set(report["methods"]) == {"bm25", "embeddings", "hybrid"}
    for name, metrics in report["methods"].items():
        for key in ("recall_at_1", "recall_at_3", "mrr"):
            assert f"{metrics[key]:.2f}" in README, (name, key)
    assert str(report["methods"]["bm25"]["n"]) in README


def test_the_full_evaluation_result_comes_from_the_report():
    report = json.loads((RESULTS / "claude-haiku-5.5-33-cases.json").read_text(encoding="utf-8"))
    assert report["total"] >= 33
    assert f"{report['passed']}/{report['total']}" in README


def test_the_readme_has_a_diagram_and_the_three_screenshots():
    assert "```mermaid" in README
    for image in ("web-interface-light.jpg", "web-interface-dark.jpg", "web-interface-dev.jpg"):
        assert f"docs/{image}" in README
        assert (ROOT / "docs" / image).stat().st_size > 10_000, image


def test_the_readme_states_the_limits_of_the_new_parts_plainly():
    limits = README[README.index("## Limitations and next steps") :].lower()
    for needle in (
        "never called",
        "word variants",
        "built only in the ci",
        "one client",
        "real phone",
    ):
        assert needle in limits, needle
