"""Runtime settings, read from the environment (and `.env` when running the CLI)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-haiku-5.5"
REFERENCE_TIME = time(10, 0)


class ConfigError(ValueError):
    """A setting has an invalid value."""


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    llm_base_url: str
    llm_api_key: str | None
    llm_model: str
    now: datetime
    today: date


def _read(env: Mapping[str, str], key: str) -> str | None:
    """Value of `key`, with blank strings treated as unset (`.env.example` ships blanks)."""
    value = env.get(key, "").strip()
    return value or None


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    if env is None:
        load_dotenv()
        env = os.environ

    today_text = _read(env, "EMPORIO_TODAY")
    if today_text is None:
        now = datetime.now()
    else:
        try:
            now = datetime.combine(date.fromisoformat(today_text), REFERENCE_TIME)
        except ValueError as exc:
            raise ConfigError(f"EMPORIO_TODAY must be YYYY-MM-DD, got {today_text!r}") from exc

    return Settings(
        data_dir=Path(_read(env, "EMPORIO_DATA_DIR") or ROOT / "data"),
        db_path=Path(_read(env, "EMPORIO_DB_PATH") or ROOT / "var" / "emporio.db"),
        llm_base_url=_read(env, "LLM_BASE_URL") or DEFAULT_BASE_URL,
        llm_api_key=_read(env, "LLM_API_KEY"),
        llm_model=_read(env, "LLM_MODEL") or DEFAULT_MODEL,
        now=now,
        today=now.date(),
    )
