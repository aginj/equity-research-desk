"""Weekday clock-time schedules per venue."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.schedule import (
    ScheduleError,
    next_weekday_at,
    parse_hhmm,
    parse_store,
    upcoming_fires,
)


def test_parse_hhmm_accepts_blank_and_valid():
    assert parse_hhmm(None) is None
    assert parse_hhmm("  ") is None
    assert parse_hhmm("09:30") == (9, 30)
    assert parse_hhmm("15:45") == (15, 45)
    assert parse_hhmm("09:30:00") == (9, 30)
    with pytest.raises(ScheduleError):
        parse_hhmm("9:30")
    with pytest.raises(ScheduleError):
        parse_hhmm("24:00")
    with pytest.raises(ScheduleError):
        parse_hhmm("09:60")


def test_parse_store_fills_all_markets_and_rejects_unknown():
    store = parse_store({"in-nse": {"morning": "09:30", "afternoon": "15:45"}})
    assert store["in-nse"]["morning"] == "09:30"
    assert store["in-nse"]["afternoon"] == "15:45"
    assert store["in-nse"]["enabled"] is True
    assert store["us"]["morning"] is None
    assert store["us"]["afternoon"] is None
    with pytest.raises(ScheduleError, match="Unknown market"):
        parse_store({"mars": {"morning": "09:00"}})
    with pytest.raises(ScheduleError, match="must differ"):
        parse_store({"us": {"morning": "10:00", "afternoon": "10:00"}})


def test_next_weekday_skips_weekend():
    # Saturday 10 May 2026 08:00 IST → next 09:30 is Monday 11 May.
    saturday = datetime(2026, 5, 10, 8, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    nxt = next_weekday_at(ZoneInfo("Asia/Kolkata"), 9, 30, now=saturday)
    assert nxt.weekday() == 0
    assert nxt.hour == 9 and nxt.minute == 30


def test_upcoming_fires_orders_soonest_first():
    now = datetime(2026, 5, 11, 8, 0, tzinfo=UTC)  # Monday
    fires = upcoming_fires(
        {
            "in-nse": {"morning": "09:30", "afternoon": "15:45"},
            "us": {"morning": None, "afternoon": None},
        },
        now=now,
    )
    assert fires
    assert fires[0].market_id == "in-nse"
    assert fires[0].slot in {"morning", "afternoon"}
    assert fires[0].timezone == "Asia/Kolkata"


def test_upcoming_fires_skips_paused_and_closed():
    now = datetime(2026, 5, 11, 8, 0, tzinfo=UTC)
    paused = upcoming_fires(
        {"in-nse": {"morning": "09:30", "afternoon": "15:45", "enabled": False}},
        now=now,
    )
    assert all(fire.market_id != "in-nse" for fire in paused)
    closed = upcoming_fires(
        {"in-nse": {"morning": "09:30", "afternoon": None, "closed_dates": ["2026-05-11"]}},
        now=now,
    )
    assert all(fire.market_id != "in-nse" for fire in closed)
