"""Spec 20: the Docker image runs the chat, keeps data in a volume and never carries the key."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
IGNORE = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_the_image_installs_the_project_with_its_data_and_starts_the_chat():
    assert DOCKERFILE.startswith("FROM python:3.12-slim")
    assert "COPY data ./data" in DOCKERFILE and "COPY src ./src" in DOCKERFILE
    assert "pip install --no-cache-dir -e ." in DOCKERFILE
    assert 'ENTRYPOINT ["emporio"]' in DOCKERFILE and 'CMD ["chat"]' in DOCKERFILE


def test_the_database_is_in_a_volume_and_the_process_is_not_root():
    assert "EMPORIO_DB_PATH=/data/emporio.db" in DOCKERFILE
    assert 'VOLUME ["/data"]' in DOCKERFILE
    assert "USER melo" in DOCKERFILE


def test_the_key_and_local_files_stay_out_of_the_image():
    for entry in (".env", ".git", ".venv", "var"):
        assert entry in IGNORE, entry
    assert "LLM_API_KEY" not in DOCKERFILE and "ARG " not in DOCKERFILE


def test_the_ci_builds_the_image_and_runs_a_smoke_test_that_needs_no_key():
    assert "docker build" in WORKFLOW
    assert "data-report" in WORKFLOW and "stats" in WORKFLOW
