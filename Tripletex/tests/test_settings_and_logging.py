import logging

from app.config import Settings
from app.logging_utils import get_logger


def test_settings_accept_env_style_initialization() -> None:
    settings = Settings(
        TRIPLETEX_AGENT_API_KEY="secret",
        TRIPLETEX_VERIFY_TLS=False,
        OPENAI_API_KEY="openai-key",
        OPENAI_BASE_URL="https://example.com/v1",
        OPENAI_MODEL="gpt-5",
    )

    assert settings.api_key == "secret"
    assert settings.verify_tls is False
    assert settings.openai_api_key == "openai-key"
    assert settings.openai_base_url == "https://example.com/v1"
    assert settings.openai_model == "gpt-5"


def test_get_logger_returns_named_logger() -> None:
    logger = get_logger("tripletex-agent.test")

    assert logger.name == "tripletex-agent.test"
    assert isinstance(logger, logging.Logger)

