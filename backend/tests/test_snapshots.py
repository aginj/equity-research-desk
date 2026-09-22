"""Rating snapshots, book diffs, and track record."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.domain import Quote, Recommendation, Scorecard
from app.snapshots import ACTION_RANK, diff_recommendations
from tests.conftest import wait_for_run


def _rec(ticker: str, action: str, conviction: float = 0.7) -> Recommendation:
    return Recommendation(
        ticker=ticker,
        name=ticker,
        sector="Technology",
        action=action,  # type: ignore[arg-type]
        conviction=conviction,
        horizon="swing_3_12m",
        thesis="Thesis for tests.",
        bull_case="Bull case for tests.",
        bear_case="Bear case for tests.",
        invalidation="Breaks if the thesis is wrong.",
        scores=Scorecard(
            news_materiality=0.5,
            fundamental_quality=0.5,
            valuation_attractiveness=0.5,
            momentum=0.5,
            risk=0.4,
            source_quality=0.5,
            composite=0.5,
        ),
        quote=Quote(
            ticker=ticker,
            price=100.0,
            change_pct=0.0,
            as_of=datetime.now(UTC),
            source="test",
        ),
    )


def test_diff_recommendations_classifies_moves():
    previous = [_rec("AAPL", "watch"), _rec("MSFT", "accumulate"), _rec("XOM", "watch")]
    current = [_rec("AAPL", "accumulate"), _rec("MSFT", "watch"), _rec("NVDA", "accumulate")]
    diff = diff_recommendations(current, previous)
    assert {row["ticker"] for row in diff["new_accumulate"]} == {"AAPL", "NVDA"}
    assert {row["ticker"] for row in diff["upgrades"]} == {"AAPL"}
    assert {row["ticker"] for row in diff["downgrades"]} == {"MSFT"}
    assert {row["ticker"] for row in diff["added"]} == {"NVDA"}
    assert {row["ticker"] for row in diff["dropped"]} == {"XOM"}
    assert ACTION_RANK["accumulate"] < ACTION_RANK["watch"]


def test_schedule_get_includes_enabled_flag(client: TestClient):
    body = client.get("/api/v1/settings/schedule").json()
    assert body["markets"]
    assert "enabled" in body["markets"][0]
    assert "closed_dates" in body["markets"][0]


def test_snapshots_written_after_run(client: TestClient):
    started = client.post("/api/v1/runs", json={"tickers": ["AAPL", "MSFT"]})
    assert started.status_code == 202
    completed = wait_for_run(client, started.json()["run_id"])
    assert completed["status"] == "completed"
    assert completed.get("triggered_by") == "api-key"
    history = client.get("/api/v1/ideas/AAPL/history").json()
    assert history["points"]
    assert history["points"][0]["run_id"] == completed["run_id"]
    changes = client.get("/api/v1/book/changes").json()
    assert "new_accumulate" in changes
    record = client.get("/api/v1/track-record").json()
    assert "horizons" in record
    assert record["market_id"] == "us"
