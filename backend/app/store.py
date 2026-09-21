"""Persistence helpers: engine lifecycle, light migrations, settings, and universe seeding."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, create_engine, select

from app.config import DATA_DIR, ROOT, get_settings
from app.data.demo import PROFILES
from app.db import (
    AnalysisRunRow,
    SettingRow,
    UniverseRow,
    UserPreferenceRow,
    UserRow,
    WatchlistRow,
    utcnow,
)
from app.domain import RiskAppetite
from app.markets import MARKETS, get_market, normalize_ticker

logger = logging.getLogger(__name__)

_engine: Engine | None = None

_APPETITES: frozenset[str] = frozenset({"conservative", "balanced", "aggressive"})
SETTING_ACTIVE_MARKET = "active_market"
SETTING_RISK_APPETITE = "risk_appetite"


def _resolve_sqlite_url(url: str) -> str:
    """Resolve relative SQLite paths against the backend root, not the process CWD."""
    prefix = "sqlite:///"
    if not url.startswith(prefix) or url == "sqlite:///:memory:":
        return url
    raw = url[len(prefix) :]
    path = Path(raw)
    if not path.is_absolute():
        path = (ROOT / raw).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"{prefix}{path.as_posix()}"


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        if url.startswith("sqlite"):
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            url = _resolve_sqlite_url(url)
            engine = create_engine(url, connect_args={"check_same_thread": False})

            @event.listens_for(engine, "connect")
            def _sqlite_pragmas(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
                cursor = dbapi_connection.cursor()
                try:
                    # WAL lets API reads proceed while a desk run is writing.
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                    cursor.execute("PRAGMA busy_timeout=5000")
                    cursor.execute("PRAGMA foreign_keys=ON")
                finally:
                    cursor.close()

        else:
            engine = create_engine(url, pool_pre_ping=True)
        _engine = engine
    return _engine


def reset_engine() -> None:
    """Dispose of the cached engine. Intended for tests."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def init_db() -> None:
    run_migrations()
    seed_universe()


def run_migrations() -> None:
    """Apply Alembic migrations against the app engine (SQLite and Postgres alike).

    Migration 0001 is idempotent so desks created with ``create_all`` before Alembic existed
    are adopted rather than rebuilt; afterwards ``alembic_version`` tracks the schema.
    """
    from alembic.config import Config

    from alembic import command

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    engine = get_engine()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    logger.info("Database schema is current", extra={"dialect": engine.dialect.name})


def get_setting(key: str, default: str) -> str:
    with Session(get_engine()) as session:
        row = session.get(SettingRow, key)
        if row and row.value:
            return row.value
    return default


def set_setting(key: str, value: str) -> None:
    with Session(get_engine()) as session:
        row = session.get(SettingRow, key)
        if row:
            row.value = value
            session.add(row)
        else:
            session.add(SettingRow(key=key, value=value))
        session.commit()


def current_market_id() -> str:
    raw = get_setting(SETTING_ACTIVE_MARKET, get_settings().default_market)
    return raw if raw in MARKETS else "us"


def current_appetite() -> RiskAppetite:
    raw = get_setting(SETTING_RISK_APPETITE, get_settings().risk_appetite)
    return raw if raw in _APPETITES else "balanced"  # type: ignore[return-value]


def set_appetite(value: RiskAppetite) -> None:
    set_setting(SETTING_RISK_APPETITE, value)


def ensure_market_universe(market_id: str) -> None:
    market = get_market(market_id)
    settings = get_settings()
    tickers = list(market.default_universe)
    if market.id == "us" and settings.universe_tickers:
        tickers = settings.universe_tickers
    with Session(get_engine()) as session:
        existing = session.exec(
            select(UniverseRow).where(UniverseRow.market_id == market.id)
        ).first()
        if existing:
            return
        for ticker in tickers:
            symbol = normalize_ticker(ticker)
            profile = PROFILES.get(symbol)
            session.add(
                UniverseRow(
                    market_id=market.id,
                    ticker=symbol,
                    name=profile.name if profile else symbol,
                    sector=profile.sector if profile else None,
                    active=True,
                )
            )
        session.commit()


def seed_universe() -> None:
    ensure_market_universe(current_market_id())


def recover_stale_runs(reason: str = "Interrupted by server restart") -> int:
    """Mark runs left in a non-terminal state (e.g. after a crash) as failed."""
    with Session(get_engine()) as session:
        rows = session.exec(
            select(AnalysisRunRow).where(col(AnalysisRunRow.status).in_(["queued", "running"]))
        ).all()
        for row in rows:
            row.status = "failed"
            row.stage = "failed"
            row.error = reason
            row.finished_at = utcnow()
            session.add(row)
        if rows:
            session.commit()
            logger.warning("Marked %d stale run(s) as failed", len(rows))
        return len(rows)


def prune_run_history(keep: int) -> int:
    """Delete the oldest runs beyond ``keep`` so the SQLite file does not grow forever."""
    with Session(get_engine()) as session:
        rows = session.exec(
            select(AnalysisRunRow).order_by(col(AnalysisRunRow.started_at).desc())
        ).all()
        stale = rows[keep:]
        for row in stale:
            session.delete(row)
        if stale:
            session.commit()
        return len(stale)


def session_factory() -> Session:
    return Session(get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


# ------------------------------------------------------------------ users & workspaces


def upsert_user(
    user_id: str,
    *,
    email: str | None,
    name: str | None,
    image: str | None,
    role: str,
) -> UserRow:
    """Create or refresh the local mirror of an authenticated user."""
    with Session(get_engine()) as session:
        row = session.get(UserRow, user_id)
        if row is None:
            row = UserRow(id=user_id, email=email, name=name, image=image, role=role)
        else:
            row.email = email or row.email
            row.name = name or row.name
            row.image = image or row.image
            row.role = role
            row.last_seen_at = utcnow()
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def get_preferences(user_id: str) -> UserPreferenceRow:
    """Return the user's workspace preferences, defaulting to the desk-wide settings."""
    with Session(get_engine()) as session:
        row = session.get(UserPreferenceRow, user_id)
        if row:
            return row
    return UserPreferenceRow(
        user_id=user_id,
        market_id=current_market_id(),
        risk_appetite=current_appetite(),
    )


def set_preferences(
    user_id: str,
    *,
    market_id: str | None = None,
    risk_appetite: str | None = None,
) -> UserPreferenceRow:
    with Session(get_engine()) as session:
        row = session.get(UserPreferenceRow, user_id)
        if row is None:
            row = UserPreferenceRow(
                user_id=user_id,
                market_id=current_market_id(),
                risk_appetite=current_appetite(),
            )
        if market_id is not None:
            row.market_id = market_id
        if risk_appetite is not None:
            row.risk_appetite = risk_appetite
        row.updated_at = utcnow()
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def list_watchlist(user_id: str, market_id: str | None = None) -> list[WatchlistRow]:
    with Session(get_engine()) as session:
        query = select(WatchlistRow).where(WatchlistRow.user_id == user_id)
        if market_id:
            query = query.where(WatchlistRow.market_id == market_id)
        return list(session.exec(query.order_by(col(WatchlistRow.added_at).desc())).all())


def add_to_watchlist(
    user_id: str, market_id: str, ticker: str, note: str | None = None
) -> WatchlistRow:
    with Session(get_engine()) as session:
        row = session.get(WatchlistRow, (user_id, market_id, ticker))
        if row is None:
            row = WatchlistRow(user_id=user_id, market_id=market_id, ticker=ticker, note=note)
        elif note is not None:
            row.note = note
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def remove_from_watchlist(user_id: str, market_id: str, ticker: str) -> bool:
    with Session(get_engine()) as session:
        row = session.get(WatchlistRow, (user_id, market_id, ticker))
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def coverage_requests() -> list[dict[str, object]]:
    """Watchlisted tickers that are not in the analyzed universe, with demand counts."""
    with Session(get_engine()) as session:
        covered = {
            (r.market_id, r.ticker)
            for r in session.exec(select(UniverseRow).where(col(UniverseRow.active).is_(True)))
        }
        counts: dict[tuple[str, str], int] = {}
        for row in session.exec(select(WatchlistRow)).all():
            key = (row.market_id, row.ticker)
            if key in covered:
                continue
            counts[key] = counts.get(key, 0) + 1
    return [
        {"market_id": market_id, "ticker": ticker, "requests": n}
        for (market_id, ticker), n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
