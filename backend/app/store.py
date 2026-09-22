"""Persistence helpers: engine lifecycle, light migrations, settings, and universe seeding."""

from __future__ import annotations

import json
import logging
import secrets
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, create_engine, select

from app.config import DATA_DIR, ROOT, get_settings
from app.data.demo import PROFILES
from app.db import (
    AnalysisRunRow,
    LocalAccountRow,
    RatingSnapshotRow,
    SettingRow,
    UniverseRow,
    UserPreferenceRow,
    UserRow,
    WatchlistRow,
    coerce_utc,
    utcnow,
)
from app.domain import RiskAppetite
from app.markets import MARKETS, get_market, normalize_ticker

logger = logging.getLogger(__name__)

_engine: Engine | None = None

_APPETITES: frozenset[str] = frozenset({"conservative", "balanced", "aggressive"})
SETTING_ACTIVE_MARKET = "active_market"
SETTING_RISK_APPETITE = "risk_appetite"
# HMAC key for local username/password sessions when SMP_AUTH_JWT_SECRET is unset.
SETTING_JWT_SECRET = "auth_jwt_secret"
SETTING_MARKET_SCHEDULE = "market_schedule"
SETTING_SCHEDULE_STATE = "schedule_state"


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
    from app.snapshots import backfill_snapshots

    backfill_snapshots()
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


def get_market_schedule() -> dict[str, dict]:
    from app.schedule import ScheduleError, empty_store, parse_store

    raw = get_setting(SETTING_MARKET_SCHEDULE, "")
    if not raw:
        return empty_store()
    try:
        payload = json.loads(raw)
        return parse_store(payload)
    except (json.JSONDecodeError, ScheduleError):
        return empty_store()


def set_market_schedule(store: dict[str, dict]) -> dict[str, dict]:
    from app.schedule import parse_store

    normalized = parse_store(store)
    set_setting(SETTING_MARKET_SCHEDULE, json.dumps(normalized, separators=(",", ":")))
    return normalized


def get_schedule_state() -> dict:
    raw = get_setting(SETTING_SCHEDULE_STATE, "")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def record_schedule_fire(
    market_id: str,
    slot: str,
    *,
    run_id: str | None,
    status: str,
) -> None:
    state = get_schedule_state()
    venue = state.setdefault(market_id, {})
    venue[slot] = {
        "last_fired_at": utcnow().isoformat(),
        "last_run_id": run_id,
        "last_status": status,
    }
    set_setting(SETTING_SCHEDULE_STATE, json.dumps(state, separators=(",", ":")))


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
            for snap in session.exec(
                select(RatingSnapshotRow).where(RatingSnapshotRow.run_id == row.id)
            ).all():
                session.delete(snap)
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


def local_account_count() -> int:
    with Session(get_engine()) as session:
        return len(list(session.exec(select(LocalAccountRow)).all()))


def get_local_account(user_id: str) -> LocalAccountRow | None:
    with Session(get_engine()) as session:
        return session.get(LocalAccountRow, user_id)


def get_local_account_by_username(username: str) -> LocalAccountRow | None:
    key = username.strip().lower()
    with Session(get_engine()) as session:
        return session.exec(select(LocalAccountRow).where(LocalAccountRow.username == key)).first()


def create_local_account(
    *,
    user_id: str,
    username: str,
    password_hash: str,
    role: str,
    email: str | None,
    name: str | None,
) -> LocalAccountRow:
    """Create the app_user mirror and the local credential row together."""
    upsert_user(user_id, email=email, name=name, image=None, role=role)
    with Session(get_engine()) as session:
        row = LocalAccountRow(
            user_id=user_id,
            username=username.strip().lower(),
            password_hash=password_hash,
            role=role,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def persisted_jwt_secret() -> str | None:
    value = get_setting(SETTING_JWT_SECRET, "")
    return value or None


def ensure_jwt_secret() -> str:
    """Return the HMAC key used to mint/verify desk API tokens.

    Prefers ``SMP_AUTH_JWT_SECRET``. Otherwise reuses (or creates) a secret stored in
    the local database so username/password login works without editing ``.env``.
    """
    env_secret = get_settings().auth_jwt_secret
    if env_secret:
        return env_secret
    existing = persisted_jwt_secret()
    if existing:
        return existing
    generated = secrets.token_urlsafe(48)
    set_setting(SETTING_JWT_SECRET, generated)
    return generated


def reset_local_auth() -> None:
    """Remove local accounts and the persisted JWT secret. Used by tests."""
    with Session(get_engine()) as session:
        for row in list(session.exec(select(LocalAccountRow)).all()):
            session.delete(row)
        secret = session.get(SettingRow, SETTING_JWT_SECRET)
        if secret:
            session.delete(secret)
        local_users = list(
            session.exec(select(UserRow).where(col(UserRow.id).like("local:%"))).all()
        )
        ids = [row.id for row in local_users]
        if ids:
            for pref in session.exec(
                select(UserPreferenceRow).where(col(UserPreferenceRow.user_id).in_(ids))
            ).all():
                session.delete(pref)
            for watch in session.exec(
                select(WatchlistRow).where(col(WatchlistRow.user_id).in_(ids))
            ).all():
                session.delete(watch)
            for row in local_users:
                session.delete(row)
        session.commit()


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


LOCKOUT_AFTER = 5
LOCKOUT_MINUTES = 15


def list_desk_users() -> list[dict]:
    with Session(get_engine()) as session:
        accounts = list(session.exec(select(LocalAccountRow)).all())
        users = {row.id: row for row in session.exec(select(UserRow)).all()}
    out = []
    for account in accounts:
        user = users.get(account.user_id)
        locked_until = coerce_utc(account.locked_until)
        out.append(
            {
                "id": account.user_id,
                "username": account.username,
                "email": user.email if user else None,
                "name": user.name if user else account.username,
                "role": account.role,
                "created_at": account.created_at.isoformat() if account.created_at else None,
                "disabled": account.disabled_at is not None,
                "locked": bool(locked_until and locked_until > utcnow()),
            }
        )
    out.sort(key=lambda item: item["username"])
    return out


def local_admin_count() -> int:
    with Session(get_engine()) as session:
        return len(
            [
                row
                for row in session.exec(
                    select(LocalAccountRow).where(LocalAccountRow.role == "admin")
                ).all()
                if row.disabled_at is None
            ]
        )


def set_local_role(user_id: str, role: str) -> LocalAccountRow:
    if role not in {"user", "admin"}:
        raise ValueError("Role must be user or admin")
    with Session(get_engine()) as session:
        row = session.get(LocalAccountRow, user_id)
        if row is None:
            raise KeyError(user_id)
        if row.role == "admin" and role != "admin" and local_admin_count() <= 1:
            raise ValueError("Cannot demote the last admin")
        row.role = role
        session.add(row)
        user = session.get(UserRow, user_id)
        if user:
            user.role = role
            session.add(user)
        session.commit()
        session.refresh(row)
        return row


def set_local_disabled(user_id: str, disabled: bool) -> LocalAccountRow:
    with Session(get_engine()) as session:
        row = session.get(LocalAccountRow, user_id)
        if row is None:
            raise KeyError(user_id)
        if disabled and row.role == "admin" and local_admin_count() <= 1:
            raise ValueError("Cannot disable the last admin")
        row.disabled_at = utcnow() if disabled else None
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def set_local_password(user_id: str, password_hash: str) -> None:
    with Session(get_engine()) as session:
        row = session.get(LocalAccountRow, user_id)
        if row is None:
            raise KeyError(user_id)
        row.password_hash = password_hash
        row.failed_logins = 0
        row.locked_until = None
        session.add(row)
        session.commit()


def record_login_failure(user_id: str) -> LocalAccountRow | None:
    with Session(get_engine()) as session:
        row = session.get(LocalAccountRow, user_id)
        if row is None:
            return None
        row.failed_logins = int(row.failed_logins or 0) + 1
        if row.failed_logins >= LOCKOUT_AFTER:
            row.locked_until = utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def clear_login_failures(user_id: str) -> None:
    with Session(get_engine()) as session:
        row = session.get(LocalAccountRow, user_id)
        if row is None:
            return
        row.failed_logins = 0
        row.locked_until = None
        session.add(row)
        session.commit()
