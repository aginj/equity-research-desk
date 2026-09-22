"""In-app notifications for watchlist changes, morning digests, and failed scheduled runs."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlmodel import Session, col, select

from app.db import LocalAccountRow, NotificationRow, UserPreferenceRow, UserRow, WatchlistRow
from app.domain import AnalysisResult
from app.snapshots import ACTION_RANK, ticker_history
from app.store import get_engine

logger = logging.getLogger(__name__)

KEEP_PER_USER = 200


def notify_run_complete(result: AnalysisResult) -> int:
    """Watchlist action changes plus a digest when the run was scheduled."""
    created = _watchlist_changes(result)
    trigger = result.triggered_by or ""
    if trigger.startswith("schedule:") or trigger == "interval":
        created += _digest(result)
    return created


def notify_run_failed(*, market_id: str, run_id: str | None, error: str) -> int:
    title = "Scheduled desk run failed"
    body = (error or "The scheduled run did not complete.")[:1800]
    count = 0
    for admin_id in _admin_user_ids():
        _create(
            user_id=admin_id,
            kind="run_failed",
            market_id=market_id,
            run_id=run_id,
            title=title,
            body=body,
        )
        count += 1
    return count


def list_notifications(
    user_id: str, *, unread_only: bool = False, limit: int = 50
) -> list[NotificationRow]:
    with Session(get_engine()) as session:
        query = select(NotificationRow).where(NotificationRow.user_id == user_id)
        if unread_only:
            query = query.where(col(NotificationRow.read_at).is_(None))
        return list(
            session.exec(query.order_by(col(NotificationRow.created_at).desc()).limit(limit)).all()
        )


def unread_count(user_id: str) -> int:
    with Session(get_engine()) as session:
        rows = session.exec(
            select(NotificationRow).where(
                NotificationRow.user_id == user_id,
                col(NotificationRow.read_at).is_(None),
            )
        ).all()
        return len(list(rows))


def mark_read(user_id: str, ids: list[str] | None = None) -> int:
    now = datetime.now(UTC)
    with Session(get_engine()) as session:
        query = select(NotificationRow).where(
            NotificationRow.user_id == user_id,
            col(NotificationRow.read_at).is_(None),
        )
        if ids:
            query = query.where(col(NotificationRow.id).in_(ids))
        rows = list(session.exec(query).all())
        for row in rows:
            row.read_at = now
            session.add(row)
        if rows:
            session.commit()
        return len(rows)


def serialize_notification(row: NotificationRow) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "market_id": row.market_id,
        "ticker": row.ticker,
        "run_id": row.run_id,
        "title": row.title,
        "body": row.body,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "read_at": row.read_at.isoformat() if row.read_at else None,
    }


def _watchlist_changes(result: AnalysisResult) -> int:
    current = {r.ticker: r.action for r in result.recommendations}
    previous: dict[str, str] = {}
    for rec in result.recommendations:
        history = ticker_history(result.market_id, rec.ticker, limit=2)
        for snap in history:
            if snap.run_id != result.run_id:
                previous[rec.ticker] = snap.action
                break
    changed = {
        ticker: (previous[ticker], action)
        for ticker, action in current.items()
        if ticker in previous and previous[ticker] != action
    }
    if not changed:
        return 0
    created = 0
    with Session(get_engine()) as session:
        watchers = list(
            session.exec(
                select(WatchlistRow).where(WatchlistRow.market_id == result.market_id)
            ).all()
        )
    for row in watchers:
        pair = changed.get(row.ticker)
        if not pair:
            continue
        old, new = pair
        upgraded = ACTION_RANK.get(new, 9) < ACTION_RANK.get(old, 9)
        direction = "upgraded" if upgraded else "downgraded"
        _create(
            user_id=row.user_id,
            kind="watchlist_change",
            market_id=result.market_id,
            ticker=row.ticker,
            run_id=result.run_id,
            title=f"{row.ticker} {direction} to {new}",
            body=f"Your watchlist name moved from {old} to {new} after the latest desk run.",
        )
        created += 1
    return created


def _digest(result: AnalysisResult) -> int:
    acc = [r.ticker for r in result.recommendations if r.action == "accumulate"][:6]
    headline = result.summary.headline if result.summary else "Desk run complete"
    body = headline
    if acc:
        body = f"{headline} Top accumulate: {', '.join(acc)}."
    created = 0
    with Session(get_engine()) as session:
        prefs = list(
            session.exec(
                select(UserPreferenceRow).where(UserPreferenceRow.market_id == result.market_id)
            ).all()
        )
    for pref in prefs:
        _create(
            user_id=pref.user_id,
            kind="digest",
            market_id=result.market_id,
            run_id=result.run_id,
            title="Morning book",
            body=body[:1800],
        )
        created += 1
    return created


def _admin_user_ids() -> list[str]:
    ids: set[str] = set()
    with Session(get_engine()) as session:
        for row in session.exec(select(UserRow).where(UserRow.role == "admin")).all():
            ids.add(row.id)
        for row in session.exec(
            select(LocalAccountRow).where(LocalAccountRow.role == "admin")
        ).all():
            ids.add(row.user_id)
    return list(ids)


def _create(
    *,
    user_id: str,
    kind: str,
    title: str,
    body: str,
    market_id: str | None = None,
    ticker: str | None = None,
    run_id: str | None = None,
) -> None:
    with Session(get_engine()) as session:
        session.add(
            NotificationRow(
                id=uuid.uuid4().hex[:16],
                user_id=user_id,
                kind=kind,
                market_id=market_id,
                ticker=ticker,
                run_id=run_id,
                title=title[:200],
                body=body[:2000],
            )
        )
        session.commit()
    _prune(user_id)


def _prune(user_id: str) -> None:
    with Session(get_engine()) as session:
        rows = list(
            session.exec(
                select(NotificationRow)
                .where(NotificationRow.user_id == user_id)
                .order_by(col(NotificationRow.created_at).desc())
            ).all()
        )
        for row in rows[KEEP_PER_USER:]:
            session.delete(row)
        if len(rows) > KEEP_PER_USER:
            session.commit()
