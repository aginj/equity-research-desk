"""Application settings. All runtime knobs live here — never hardcode keys."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

Environment = Literal["development", "staging", "production"]
RiskAppetiteSetting = Literal["conservative", "balanced", "aggressive"]

_VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            Path(__file__).resolve().parents[2] / ".env",
            ROOT / ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Equity Research Desk"
    environment: Environment = Field(default="development", alias="SMP_ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="SMP_LOG_LEVEL")
    log_json: bool = Field(default=False, alias="SMP_LOG_JSON")
    database_url: str = Field(default="sqlite:///./data/desk.db", alias="SMP_DATABASE_URL")
    cors_origins: str = Field(
        default="http://localhost:3810,http://127.0.0.1:3810,http://localhost:3811,http://127.0.0.1:3811",
        alias="SMP_CORS_ORIGINS",
    )
    # Optional machine credential. When set, admin endpoints also accept `X-API-Key`.
    api_key: str | None = Field(default=None, alias="SMP_API_KEY")
    # Shared with the web app, which mints HS256 bearer tokens after Auth.js sign-in.
    auth_jwt_secret: str | None = Field(default=None, min_length=1, alias="SMP_AUTH_JWT_SECRET")
    # Comma-separated emails granted the admin role (run desk, edit universe, defaults).
    admin_emails: str = Field(default="", alias="SMP_ADMIN_EMAILS")
    rate_limit_enabled: bool = Field(default=True, alias="SMP_RATE_LIMIT_ENABLED")
    rate_limit_default: str = Field(default="120/minute", alias="SMP_RATE_LIMIT_DEFAULT")
    rate_limit_runs: str = Field(default="5/minute", alias="SMP_RATE_LIMIT_RUNS")
    rate_limit_writes: str = Field(default="60/minute", alias="SMP_RATE_LIMIT_WRITES")

    default_universe: str = Field(
        default="AAPL,MSFT,NVDA,AMZN,GOOGL,META,AVGO,LLY,JPM,V,UNH,XOM,CAT,HD,COST,WMT,PG,JNJ,GE,GS",
        alias="SMP_DEFAULT_UNIVERSE",
    )
    default_market: str = Field(default="us", alias="SMP_DEFAULT_MARKET")
    risk_appetite: RiskAppetiteSetting = Field(default="balanced", alias="SMP_RISK_APPETITE")
    news_lookback_days: int = Field(default=5, ge=1, le=30, alias="SMP_NEWS_LOOKBACK_DAYS")
    max_news_per_ticker: int = Field(default=8, ge=1, le=50, alias="SMP_MAX_NEWS_PER_TICKER")
    max_universe_size: int = Field(default=60, ge=1, le=500, alias="SMP_MAX_UNIVERSE_SIZE")
    ingest_concurrency: int = Field(default=4, ge=1, le=32, alias="SMP_INGEST_CONCURRENCY")
    http_timeout_seconds: float = Field(default=12.0, gt=0, le=120, alias="SMP_HTTP_TIMEOUT")
    llm_timeout_seconds: float = Field(default=60.0, gt=0, le=600, alias="SMP_LLM_TIMEOUT")
    force_demo_data: bool = Field(default=False, alias="SMP_FORCE_DEMO_DATA")
    sec_user_agent: str = Field(
        default="Equity Research Desk local-dev contact@example.com",
        alias="SMP_SEC_USER_AGENT",
    )
    scheduler_hours: int = Field(default=0, ge=0, le=24 * 30, alias="SMP_SCHEDULER_HOURS")
    run_history_limit: int = Field(default=200, ge=1, le=10_000, alias="SMP_RUN_HISTORY_LIMIT")
    llm_max_calls_per_run: int = Field(
        default=0, ge=0, le=10_000, alias="SMP_LLM_MAX_CALLS_PER_RUN"
    )

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="SMP_OPENAI_MODEL")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-sonnet-4-5", alias="SMP_ANTHROPIC_MODEL")
    cursor_api_key: str | None = Field(default=None, alias="CURSOR_API_KEY")
    cursor_model: str = Field(default="composer-2.5", alias="SMP_CURSOR_MODEL")
    # Optional OpenAI-compatible proxy (Cursor has no public /v1/chat/completions).
    cursor_base_url: str | None = Field(default=None, alias="SMP_CURSOR_BASE_URL")
    llm_base_url: str | None = Field(default=None, alias="SMP_LLM_BASE_URL")
    llm_api_key: str | None = Field(default=None, alias="SMP_LLM_API_KEY")
    llm_model: str | None = Field(default=None, alias="SMP_LLM_MODEL")

    finnhub_api_key: str | None = Field(default=None, alias="FINNHUB_API_KEY")
    newsapi_key: str | None = Field(default=None, alias="NEWSAPI_KEY")
    alphavantage_api_key: str | None = Field(default=None, alias="ALPHAVANTAGE_API_KEY")

    @field_validator(
        "api_key",
        "auth_jwt_secret",
        "openai_api_key",
        "anthropic_api_key",
        "cursor_api_key",
        "cursor_base_url",
        "llm_base_url",
        "llm_api_key",
        "llm_model",
        "finnhub_api_key",
        "newsapi_key",
        "alphavantage_api_key",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        """Treat `KEY=` in a .env file as unset rather than an empty credential."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        upper = value.strip().upper()
        if upper not in _VALID_LOG_LEVELS:
            raise ValueError(f"SMP_LOG_LEVEL must be one of {sorted(_VALID_LOG_LEVELS)}")
        return upper

    @model_validator(mode="after")
    def _validate_cors(self) -> Settings:
        origins = self.cors_origin_list
        if "*" in origins and len(origins) > 1:
            raise ValueError("SMP_CORS_ORIGINS cannot mix '*' with explicit origins")
        if self.is_production and "*" in origins:
            raise ValueError("SMP_CORS_ORIGINS='*' is not allowed when SMP_ENVIRONMENT=production")
        return self

    @model_validator(mode="after")
    def _validate_auth(self) -> Settings:
        if self.is_production and not (self.auth_jwt_secret or self.api_key):
            raise ValueError(
                "Production requires SMP_AUTH_JWT_SECRET (web sign-in) or SMP_API_KEY; "
                "otherwise anyone on the internet could trigger desk runs."
            )
        if self.auth_jwt_secret and len(self.auth_jwt_secret) < 32:
            raise ValueError("SMP_AUTH_JWT_SECRET must be at least 32 characters")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def log_level_int(self) -> int:
        return logging.getLevelName(self.log_level)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def cors_allow_credentials(self) -> bool:
        # Browsers reject `Access-Control-Allow-Origin: *` together with credentials.
        return "*" not in self.cors_origin_list

    @property
    def universe_tickers(self) -> list[str]:
        return [t.strip().upper() for t in self.default_universe.split(",") if t.strip()]

    @property
    def has_live_market(self) -> bool:
        return bool(self.finnhub_api_key or self.alphavantage_api_key or self.newsapi_key)

    @property
    def has_llm(self) -> bool:
        return bool(
            self.openai_api_key or self.anthropic_api_key or self.cursor_api_key or self.llm_api_key
        )

    @property
    def requires_api_key(self) -> bool:
        return bool(self.api_key)

    @property
    def auth_enabled(self) -> bool:
        """True when the API can verify bearer tokens from the web app."""
        return bool(self.auth_jwt_secret)

    @property
    def admin_email_set(self) -> frozenset[str]:
        return frozenset(
            item.strip().lower() for item in self.admin_emails.split(",") if item.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
