from datetime import UTC, datetime

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


def coerce_utc(value: datetime | None) -> datetime | None:
    """SQLite often returns naive timestamps; treat those as UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


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
    triggered_by: str | None = Field(default=None, max_length=80)


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


class LocalAccountRow(SQLModel, table=True):
    """Username/password account stored in the desk database (hashed password only)."""

    __tablename__ = "local_account"

    user_id: str = Field(primary_key=True, foreign_key="app_user.id", max_length=64)
    username: str = Field(unique=True, index=True, max_length=32)
    password_hash: str = Field(max_length=255)
    role: str = Field(default="user", max_length=16)
    created_at: datetime = Field(default_factory=utcnow)
    disabled_at: datetime | None = None
    failed_logins: int = 0
    locked_until: datetime | None = None


class RatingSnapshotRow(SQLModel, table=True):
    """Per-ticker rating at the end of a completed run. Used for history and diffs."""

    __tablename__ = "rating_snapshot"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True, max_length=32, foreign_key="analysisrunrow.id")
    market_id: str = Field(index=True, max_length=32)
    ticker: str = Field(index=True, max_length=32)
    action: str = Field(max_length=16)
    conviction: float = 0.0
    price: float = 0.0
    currency: str = Field(default="USD", max_length=8)
    sector: str | None = Field(default=None, max_length=80)
    finished_at: datetime = Field(index=True)


class NotificationRow(SQLModel, table=True):
    """In-app notification for a signed-in user."""

    __tablename__ = "notification"

    id: str = Field(primary_key=True, max_length=32)
    user_id: str = Field(index=True, max_length=64)
    kind: str = Field(max_length=32)
    market_id: str | None = Field(default=None, max_length=32)
    ticker: str | None = Field(default=None, max_length=32)
    run_id: str | None = Field(default=None, max_length=32)
    title: str = Field(max_length=200)
    body: str = Field(max_length=2000)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    read_at: datetime | None = None


class AuditLogRow(SQLModel, table=True):
    """Admin mutation trail."""

    __tablename__ = "audit_log"

    id: str = Field(primary_key=True, max_length=32)
    at: datetime = Field(default_factory=utcnow, index=True)
    actor_id: str = Field(max_length=64)
    action: str = Field(max_length=64)
    target: str = Field(default="", max_length=200)
    detail_json: str | None = Field(default=None, sa_column=Column(Text))
