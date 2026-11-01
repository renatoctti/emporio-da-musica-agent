from datetime import date, datetime
from pathlib import Path

import pytest

from emporio.config import ConfigError, load_settings

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "anthropic/claude-haiku-5.5"


def test_defaults():
    s = load_settings({})
    assert s.data_dir == ROOT / "data"
    assert s.db_path == ROOT / "var" / "emporio.db"
    assert s.llm_base_url == "https://openrouter.ai/api/v1"
    assert s.llm_api_key is None
    assert s.llm_model == DEFAULT_MODEL
    assert s.today == s.now.date()


def test_empty_values_are_unset_and_today_is_fixed():
    env = {
        "LLM_MODEL": "",
        "LLM_BASE_URL": "   ",
        "LLM_API_KEY": "",
        "EMPORIO_TODAY": "2026-03-25",
    }
    s = load_settings(env)
    assert s.llm_model == DEFAULT_MODEL
    assert s.llm_base_url == "https://openrouter.ai/api/v1"
    assert s.llm_api_key is None
    assert s.today == date(2026, 3, 25)
    assert s.now == datetime(2026, 3, 25, 10, 0)


def test_overrides_are_read():
    env = {
        "EMPORIO_DATA_DIR": "/tmp/x",
        "EMPORIO_DB_PATH": "/tmp/y.db",
        "LLM_API_KEY": "k",
        "LLM_MODEL": "m",
        "LLM_BASE_URL": "http://localhost:1/v1",
    }
    s = load_settings(env)
    assert s.data_dir == Path("/tmp/x")
    assert s.db_path == Path("/tmp/y.db")
    assert (s.llm_api_key, s.llm_model, s.llm_base_url) == ("k", "m", "http://localhost:1/v1")


@pytest.mark.parametrize("bad", ["25/03/2026", "x", "2026-13-40"])
def test_invalid_today_raises_config_error(bad):
    with pytest.raises(ConfigError, match="EMPORIO_TODAY"):
        load_settings({"EMPORIO_TODAY": bad})
