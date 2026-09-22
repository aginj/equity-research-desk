"""Per-ticker rating snapshots written when a desk run completes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlmodel import Session, col, select

from app.db import AnalysisRunRow, RatingSnapshotRow
from app.domain import AnalysisResult, Recommendation
from app.store import get_engine

logger = logging.getLogger(__name__)

ACTION_RANK: dict[str, int] = {"accumulate": 0, "watch": 1, "reduce": 2, "avoid": 3}


def record_snapshots(result: AnalysisResult) -> int:
    """Replace snapshot rows for ``result.run_id``. No-op unless the run completed."""
    if result.status != "completed" or not result.recommendations:
        return 0
    finished = result.finished_at or datetime.now(UTC)
    with Session(get_engine()) as session:
        existing = list(
            session.exec(
                select(RatingSnapshotRow).where(RatingSnapshotRow.run_id == result.run_id)
            ).all()
        )
        for row in existing:
            session.delete(row)
        count = 0
        for rec in result.recommendations:
            session.add(
                RatingSnapshotRow(
                    run_id=result.run_id,
                    market_id=result.market_id,
                    ticker=rec.ticker,
                    action=rec.action,
                    conviction=rec.conviction,
                    price=rec.quote.price,
                    currency=rec.quote.currency,
                    sector=rec.sector,
                    finished_at=finished,
                )
            )
            count += 1
        session.commit()
        return count


def backfill_snapshots() -> int:
    """Write snapshots for completed runs that do not have any yet."""
    written = 0
    with Session(get_engine()) as session:
        have = {
            run_id
            for run_id in session.exec(select(RatingSnapshotRow.run_id).distinct()).all()
            if run_id
        }
        rows = session.exec(
            select(AnalysisRunRow).where(
                AnalysisRunRow.status == "completed",
                col(AnalysisRunRow.payload_json).is_not(None),
            )
        ).all()
    for row in rows:
        if row.id in have:
            continue
        try:
            result = AnalysisResult.model_validate_json(row.payload_json or "")
        except ValueError:
            continue
        written += record_snapshots(result)
    if written:
        logger.info("Backfilled %d rating snapshot row(s)", written)
    return written


def ticker_history(market_id: str, ticker: str, limit: int = 40) -> list[RatingSnapshotRow]:
    symbol = ticker.strip().upper()
    with Session(get_engine()) as session:
        return list(
            session.exec(
                select(RatingSnapshotRow)
                .where(
                    RatingSnapshotRow.market_id == market_id,
                    RatingSnapshotRow.ticker == symbol,
                )
                .order_by(col(RatingSnapshotRow.finished_at).desc())
                .limit(limit)
            ).all()
        )


def serialize_snapshot(row: RatingSnapshotRow) -> dict:
    return {
        "run_id": row.run_id,
        "market_id": row.market_id,
        "ticker": row.ticker,
        "action": row.action,
        "conviction": row.conviction,
        "price": row.price,
        "currency": row.currency,
        "sector": row.sector,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def _change_item(rec: Recommendation, previous: Recommendation | None = None) -> dict:
    item = {
        "ticker": rec.ticker,
        "name": rec.name,
        "action": rec.action,
        "conviction": rec.conviction,
        "sector": rec.sector,
    }
    if previous is not None:
        item["previous_action"] = previous.action
        item["previous_conviction"] = previous.conviction
    return item


def diff_recommendations(
    current: list[Recommendation], previous: list[Recommendation]
) -> dict[str, list[dict]]:
    """Compare two books (already re-policied under the same appetite)."""
    curr = {r.ticker: r for r in current}
    prev = {r.ticker: r for r in previous}
    new_accumulate: list[dict] = []
    upgrades: list[dict] = []
    downgrades: list[dict] = []
    added: list[dict] = []
    dropped: list[dict] = []

    for ticker, rec in curr.items():
        old = prev.get(ticker)
        if old is None:
            added.append(_change_item(rec))
            if rec.action == "accumulate":
                new_accumulate.append(_change_item(rec))
            continue
        if rec.action == "accumulate" and old.action != "accumulate":
            new_accumulate.append(_change_item(rec, old))
        old_rank = ACTION_RANK.get(old.action, 9)
        new_rank = ACTION_RANK.get(rec.action, 9)
        if new_rank < old_rank:
            upgrades.append(_change_item(rec, old))
        elif new_rank > old_rank:
            downgrades.append(_change_item(rec, old))

    for ticker, rec in prev.items():
        if ticker not in curr:
            dropped.append(_change_item(rec))

    return {
        "new_accumulate": new_accumulate,
        "upgrades": upgrades,
        "downgrades": downgrades,
        "added": added,
        "dropped": dropped,
    }


def track_record(market_id: str) -> dict:
    """Forward returns of past accumulate calls using later snapshots of the same ticker."""
    with Session(get_engine()) as session:
        rows = list(
            session.exec(
                select(RatingSnapshotRow)
                .where(RatingSnapshotRow.market_id == market_id)
                .order_by(col(RatingSnapshotRow.finished_at).asc())
            ).all()
        )
    by_ticker: dict[str, list[RatingSnapshotRow]] = {}
    for row in rows:
        by_ticker.setdefault(row.ticker, []).append(row)

    horizons = (30, 90, 180)
    buckets: dict[int, list[float]] = {h: [] for h in horizons}

    for series in by_ticker.values():
        for i, snap in enumerate(series):
            if snap.action != "accumulate" or snap.price <= 0:
                continue
            for later in series[i + 1 :]:
                if later.price <= 0:
                    continue
                if later.finished_at is None or snap.finished_at is None:
                    continue
                days = (later.finished_at - snap.finished_at).total_seconds() / 86400
                ret = (later.price / snap.price) - 1
                for horizon in horizons:
                    if days >= horizon * 0.85:
                        buckets[horizon].append(ret)
                        break

    def _bucket(values: list[float]) -> dict:
        if not values:
            return {"n": 0, "mean_return": None, "hit_rate": None}
        hits = sum(1 for v in values if v > 0)
        return {
            "n": len(values),
            "mean_return": round(sum(values) / len(values), 4),
            "hit_rate": round(hits / len(values), 4),
        }

    return {
        "market_id": market_id,
        "as_of": datetime.now(UTC).isoformat(),
        "horizons": {str(h): _bucket(buckets[h]) for h in horizons},
        "caveat": (
            "Research record only — not a live portfolio. Returns are mark-to-snapshot "
            "inside the analyzed universe, not versus a benchmark."
        ),
    }


def previous_completed_pair(market_id: str) -> tuple[AnalysisRunRow, AnalysisRunRow] | None:
    """Latest two completed runs for a venue, newest first."""
    with Session(get_engine()) as session:
        rows = list(
            session.exec(
                select(AnalysisRunRow)
                .where(
                    AnalysisRunRow.market_id == market_id,
                    AnalysisRunRow.status == "completed",
                    col(AnalysisRunRow.payload_json).is_not(None),
                )
                .order_by(col(AnalysisRunRow.started_at).desc())
                .limit(2)
            ).all()
        )
    if len(rows) < 2:
        return None
    return rows[0], rows[1]
