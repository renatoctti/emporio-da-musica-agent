"""Spec 18: the CI workflow runs the same gate the author runs by hand."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_the_workflow_exists_and_runs_on_push_to_main_and_on_pull_requests():
    text = _text()
    assert WORKFLOW.is_file()
    assert "push:" in text and "branches: [main]" in text
    assert "pull_request:" in text


def test_it_installs_the_dev_extras_and_runs_the_three_commands_of_the_gate():
    text = _text()
    assert 'pip install -e ".[dev]"' in text
    assert "ruff check ." in text
    assert "ruff format --check ." in text
    assert "pytest" in text


def test_it_covers_python_311_and_312():
    text = _text()
    assert '"3.11"' in text and '"3.12"' in text


def test_it_is_read_only_uses_no_secret_and_only_official_actions():
    text = _text()
    assert "contents: read" in text
    assert "secrets." not in text
    uses = [line.split("uses:")[1].strip() for line in text.splitlines() if "uses:" in line]
    assert uses and all(item.startswith("actions/") for item in uses)


def test_the_readme_shows_the_workflow_status():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "actions/workflows/ci.yml" in readme


EVALS = ROOT / ".github" / "workflows" / "evals.yml"


def test_the_eval_workflow_runs_by_hand_or_weekly_and_never_on_a_pull_request():
    text = EVALS.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text and "schedule:" in text
    assert "pull_request" not in text and "push:" not in text
    assert "contents: read" in text
    assert "--fail-under" in text and "--baseline" in text
    assert text.count("secrets.") == 1  # the key reaches only the step that calls the model


JUDGE = ROOT / ".github" / "workflows" / "judge.yml"


def test_the_judge_workflow_never_runs_for_a_fork_and_uses_the_key_once():
    text = JUDGE.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text and "pull_request:" in text
    assert "head.repo.full_name == github.repository" in text
    assert "contents: read" in text
    assert text.count("secrets.") == 1
