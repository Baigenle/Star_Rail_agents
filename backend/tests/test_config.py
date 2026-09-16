from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_admin_usernames_accepts_empty_and_comma_separated_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ADMIN_USERNAMES", "")
    assert Settings().admin_usernames == ""

    monkeypatch.setenv("ADMIN_USERNAMES", "herta, curator")
    assert Settings().admin_usernames == "herta, curator"


def test_deepseek_has_separate_flash_and_pro_models(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_FLASH_MODEL", "deepseek-flash-test")
    monkeypatch.setenv("DEEPSEEK_PRO_MODEL", "deepseek-pro-test")

    configured = Settings()

    assert configured.deepseek_flash_model == "deepseek-flash-test"
    assert configured.deepseek_pro_model == "deepseek-pro-test"


def test_fc_is_the_default_main_agent_and_invalid_values_fail_fast(
    monkeypatch,
) -> None:
    monkeypatch.delenv("MAIN_AGENT_IMPL", raising=False)
    monkeypatch.delenv("DEFAULT_LLM_PROVIDER", raising=False)

    configured = Settings(_env_file=None)

    assert configured.main_agent_impl == "fc"
    assert configured.default_llm_provider == "mock"

    monkeypatch.setenv("MAIN_AGENT_IMPL", "typo")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    monkeypatch.setenv("MAIN_AGENT_IMPL", "fc")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "unknown-provider")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_example_environment_is_loadable(monkeypatch) -> None:
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)

    configured = Settings(_env_file=PROJECT_ROOT / ".env.example")

    assert configured.main_agent_impl == "fc"
    assert configured.backend_cors_origins == [
        "http://localhost:5173",
        "http://localhost:8030",
    ]
