import pytest

from app.config import Settings


def _settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)


def test_blank_keys_are_treated_as_unset():
    settings = _settings(
        OPENAI_API_KEY="  ",
        FINNHUB_API_KEY="",
        SMP_API_KEY="",
        CURSOR_API_KEY=" ",
        SMP_CURSOR_BASE_URL="",
    )
    assert settings.openai_api_key is None
    assert settings.finnhub_api_key is None
    assert settings.cursor_api_key is None
    assert settings.cursor_base_url is None
    assert settings.has_llm is False
    assert settings.requires_api_key is False


def test_cursor_key_enables_llm():
    settings = _settings(CURSOR_API_KEY="cursor_test_key")
    assert settings.has_llm is True
    assert settings.cursor_api_key == "cursor_test_key"
    assert settings.cursor_model == "composer-2.5"


def test_log_level_is_validated():
    assert _settings(SMP_LOG_LEVEL="debug").log_level == "DEBUG"
    with pytest.raises(ValueError):
        _settings(SMP_LOG_LEVEL="loud")


def test_risk_appetite_is_validated():
    with pytest.raises(ValueError):
        _settings(SMP_RISK_APPETITE="yolo")


def test_wildcard_cors_disallowed_in_production():
    secret = {"SMP_AUTH_JWT_SECRET": "x" * 40}
    with pytest.raises(ValueError, match="CORS"):
        _settings(SMP_ENVIRONMENT="production", SMP_CORS_ORIGINS="*", **secret)
    ok = _settings(
        SMP_ENVIRONMENT="production", SMP_CORS_ORIGINS="https://desk.example.com", **secret
    )
    assert ok.cors_origin_list == ["https://desk.example.com"]
    assert ok.cors_allow_credentials is True


def test_wildcard_cors_disables_credentials():
    settings = _settings(SMP_CORS_ORIGINS="*")
    assert settings.cors_allow_credentials is False


def test_numeric_bounds():
    with pytest.raises(ValueError):
        _settings(SMP_NEWS_LOOKBACK_DAYS="0")
    with pytest.raises(ValueError):
        _settings(SMP_HTTP_TIMEOUT="0")
