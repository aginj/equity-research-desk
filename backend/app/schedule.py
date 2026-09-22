"""Per-market clock-time desk runs (two optional weekday times in the venue's timezone)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.markets import MARKETS, MarketSpec, catalog_payload, get_market

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?$")
SLOTS = ("morning", "afternoon")


class ScheduleError(ValueError):
    """Invalid schedule payload from the admin UI."""


@dataclass(frozen=True, slots=True)
class MarketSchedule:
    market_id: str
    label: str
    timezone: str
    morning: str | None
    afternoon: str | None
    enabled: bool = True
    closed_dates: tuple[str, ...] = ()

    @property
    def times(self) -> tuple[str | None, str | None]:
        return (self.morning, self.afternoon)

    def has_jobs(self) -> bool:
        return self.enabled and bool(self.morning or self.afternoon)


@dataclass(frozen=True, slots=True)
class ScheduledFire:
    market_id: str
    label: str
    slot: str
    at: datetime
    local_time: str
    timezone: str


def parse_hhmm(value: str | None) -> tuple[int, int] | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = _TIME_RE.match(text)
    if not match:
        raise ScheduleError(f"Invalid time '{value}'; use HH:MM (24-hour)")
    return int(match.group(1)), int(match.group(2))


def format_hhmm(hour: int, minute: int) -> str:
    return f"{hour:02d}:{minute:02d}"


def listed_markets() -> list[MarketSpec]:
    """Catalog order (US and India pinned first)."""
    payload = catalog_payload()
    return [get_market(row["id"]) for country in payload["countries"] for row in country["markets"]]


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ScheduleError(f"Unknown timezone '{name}'") from exc


def next_weekday_at(
    tz: ZoneInfo, hour: int, minute: int, *, now: datetime | None = None
) -> datetime:
    """Next Mon–Fri occurrence of hour:minute in ``tz`` (aware)."""
    current = now.astimezone(tz) if now else datetime.now(tz)
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= current:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _closed_dates(raw: object) -> list[str]:
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ScheduleError("closed_dates must be a list of YYYY-MM-DD strings")
    out: list[str] = []
    for item in raw:
        text = str(item).strip()
        if not text:
            continue
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError as exc:
            raise ScheduleError(f"Invalid closed date '{text}'") from exc
        if text not in out:
            out.append(text)
    return out


def empty_store() -> dict[str, dict]:
    return {
        spec.id: {"morning": None, "afternoon": None, "enabled": True, "closed_dates": []}
        for spec in listed_markets()
    }


def parse_store(raw: object) -> dict[str, dict]:
    """Coerce persisted JSON into a complete {market_id: times} map."""
    base = empty_store()
    if not raw:
        return base
    if not isinstance(raw, dict):
        raise ScheduleError("Schedule must be an object of market_id → times")
    for market_id, times in raw.items():
        if market_id not in MARKETS:
            raise ScheduleError(f"Unknown market '{market_id}'")
        if times is None:
            continue
        if not isinstance(times, dict):
            raise ScheduleError(f"Times for '{market_id}' must be an object")
        morning = parse_hhmm(times.get("morning"))
        afternoon = parse_hhmm(times.get("afternoon"))
        morning_s = format_hhmm(*morning) if morning else None
        afternoon_s = format_hhmm(*afternoon) if afternoon else None
        if morning_s and afternoon_s and morning_s == afternoon_s:
            raise ScheduleError(f"{market_id}: morning and afternoon must differ")
        enabled = times.get("enabled", True)
        if not isinstance(enabled, bool):
            enabled = str(enabled).strip().lower() not in {"0", "false", "no", "off"}
        base[market_id] = {
            "morning": morning_s,
            "afternoon": afternoon_s,
            "enabled": bool(enabled),
            "closed_dates": _closed_dates(times.get("closed_dates")),
        }
    return base


def rows_from_store(store: dict[str, dict]) -> list[MarketSchedule]:
    rows: list[MarketSchedule] = []
    for spec in listed_markets():
        times = store.get(spec.id) or {}
        closed = times.get("closed_dates") or []
        rows.append(
            MarketSchedule(
                market_id=spec.id,
                label=spec.label,
                timezone=spec.timezone,
                morning=times.get("morning") if isinstance(times.get("morning"), str) else None,
                afternoon=(
                    times.get("afternoon") if isinstance(times.get("afternoon"), str) else None
                ),
                enabled=bool(times.get("enabled", True)),
                closed_dates=tuple(closed) if isinstance(closed, list) else (),
            )
        )
    return rows


def upcoming_fires(
    store: dict[str, dict],
    *,
    limit: int = 8,
    now: datetime | None = None,
) -> list[ScheduledFire]:
    origin = now or datetime.now(UTC)
    fires: list[ScheduledFire] = []
    for row in rows_from_store(store):
        if not row.enabled:
            continue
        tz = _zone(row.timezone)
        today = (now or datetime.now(UTC)).astimezone(tz).date().isoformat()
        if today in row.closed_dates:
            continue
        for slot in SLOTS:
            stamp = getattr(row, slot)
            parsed = parse_hhmm(stamp)
            if not parsed:
                continue
            hour, minute = parsed
            at = next_weekday_at(tz, hour, minute, now=origin)
            fires.append(
                ScheduledFire(
                    market_id=row.market_id,
                    label=row.label,
                    slot=slot,
                    at=at.astimezone(UTC),
                    local_time=format_hhmm(hour, minute),
                    timezone=row.timezone,
                )
            )
    fires.sort(key=lambda item: (item.at, item.market_id, item.slot))
    return fires[:limit]


def serialize_row(row: MarketSchedule) -> dict:
    return {
        "market_id": row.market_id,
        "label": row.label,
        "timezone": row.timezone,
        "morning": row.morning,
        "afternoon": row.afternoon,
        "enabled": row.enabled,
        "closed_dates": list(row.closed_dates),
    }


def serialize_fire(fire: ScheduledFire) -> dict:
    return {
        "market_id": fire.market_id,
        "label": fire.label,
        "slot": fire.slot,
        "at": fire.at.isoformat(),
        "local_time": fire.local_time,
        "timezone": fire.timezone,
    }


def payload(store: dict[str, dict], *, interval_hours: int = 0, state: dict | None = None) -> dict:
    fires = upcoming_fires(store)
    markets = []
    for row in rows_from_store(store):
        item = serialize_row(row)
        last = (state or {}).get(row.market_id) or {}
        item["last"] = last
        markets.append(item)
    return {
        "markets": markets,
        "next": [serialize_fire(fire) for fire in fires],
        "interval_hours": interval_hours if not has_clock_jobs(store) else 0,
        "clock": has_clock_jobs(store),
    }


def has_clock_jobs(store: dict[str, dict]) -> bool:
    return any(
        times.get("enabled", True) and (times.get("morning") or times.get("afternoon"))
        for times in store.values()
    )


def is_closed(store: dict[str, dict], market_id: str, *, now: datetime | None = None) -> bool:
    times = store.get(market_id) or {}
    if times.get("enabled", True) is False:
        return True
    spec = get_market(market_id)
    tz = _zone(spec.timezone)
    today = (now or datetime.now(UTC)).astimezone(tz).date().isoformat()
    closed = times.get("closed_dates") or []
    return today in closed
