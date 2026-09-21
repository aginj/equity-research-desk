from datetime import UTC, datetime

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class UniverseRow(SQLModel, table=True):
    """Tickers the desk analyzes for a venue. Admin-controlled; drives run cost."""

    market_id: str = Field(primary_key=True)
    ticker: str = Field(primary_key=True)
    name: str | None = None
    sector: str | None = None
    active: bool = True
    added_at: datetime = Field(default_factory=utcnow)


class AnalysisRunRow(SQLModel, table=True):
    id: str = Field(primary_key=True)
    status: str = Field(index=True)
    stage: str
    risk_appetite: str
    market_id: str = Field(default="us", index=True)
    started_at: datetime = Field(index=True)
    finished_at: datetime | None = None
    error: str | None = None
    payload_json: str | None = Field(default=None, sa_column=Column(Text))


class SettingRow(SQLModel, table=True):
    """Global desk defaults (active market, appetite) — admin-only."""

    key: str = Field(primary_key=True)
    value: str


class UserRow(SQLModel, table=True):
    """Mirror of the Auth.js user, keyed by the `sub` claim. Created lazily on first API use."""

    __tablename__ = "app_user"

    id: str = Field(primary_key=True, max_length=64)
    email: str | None = Field(default=None, index=True, max_length=320)
    name: str | None = Field(default=None, max_length=200)
    image: str | None = Field(default=None, max_length=2000)
    role: str = Field(default="user", max_length=16)
    created_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow)


class UserPreferenceRow(SQLModel, table=True):
    """Per-user workspace: which venue they follow and which policy appetite they view under."""

    __tablename__ = "user_preference"

    user_id: str = Field(primary_key=True, foreign_key="app_user.id", max_length=64)
    market_id: str = Field(default="us", max_length=32)
    risk_appetite: str = Field(default="balanced", max_length=16)
    updated_at: datetime = Field(default_factory=utcnow)


class WatchlistRow(SQLModel, table=True):
    """Tickers a user has starred for a venue. Does not affect what the desk analyzes."""

    __tablename__ = "watchlist"

    user_id: str = Field(primary_key=True, foreign_key="app_user.id", max_length=64)
    market_id: str = Field(primary_key=True, max_length=32)
    ticker: str = Field(primary_key=True, max_length=32)
    note: str | None = Field(default=None, max_length=500)
    added_at: datetime = Field(default_factory=utcnow)
