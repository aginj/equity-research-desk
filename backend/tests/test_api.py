import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.conftest import wait_for_run


def test_health(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["force_demo"] is True
    assert "version" in body
    assert response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_request_id_is_propagated(client: TestClient):
    response = client.get("/api/v1/markets", headers={"X-Request-ID": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"


def test_not_found_includes_request_id(client: TestClient):
    response = client.get("/api/v1/runs/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "Run not found"
    assert body["request_id"] == response.headers["x-request-id"]


def test_universe_seeded(client: TestClient):
    response = client.get("/api/v1/universe")
    assert response.status_code == 200
    tickers = {row["ticker"] for row in response.json()}
    assert "AAPL" in tickers
    assert "MSFT" in tickers


def test_universe_rejects_invalid_symbols(client: TestClient):
    response = client.put("/api/v1/universe", json={"tickers": ["AAPL", "DROP TABLE"]})
    assert response.status_code == 422
    assert "Invalid ticker" in response.json()["detail"]

    response = client.put("/api/v1/universe", json={"tickers": ["  ", ""]})
    assert response.status_code == 400


def test_universe_dedupes_and_normalizes(client: TestClient):
    original = [row["ticker"] for row in client.get("/api/v1/universe").json()]
    try:
        response = client.put("/api/v1/universe", json={"tickers": [" aapl", "AAPL", "msft "]})
        assert response.status_code == 200
        assert [row["ticker"] for row in response.json()] == ["AAPL", "MSFT"]
    finally:
        client.put("/api/v1/universe", json={"tickers": original})


def test_desk_run_completes(client: TestClient):
    started = client.post("/api/v1/runs", json={"tickers": ["AAPL", "MSFT", "JPM"]})
    assert started.status_code == 202
    run_id = started.json()["run_id"]

    completed = wait_for_run(client, run_id)
    assert completed["status"] == "completed"
    assert completed["recommendations"]
    assert completed["summary"]["tickers_analyzed"] == 3
    actions = {row["action"] for row in completed["recommendations"]}
    assert actions <= {"accumulate", "watch", "reduce", "avoid"}
    first = completed["recommendations"][0]
    assert first["sources"]
    assert first["thesis"]
    assert first["invalidation"]

    latest = client.get("/api/v1/runs/latest")
    assert latest.status_code == 200
    assert latest.json()["run_id"] == run_id

    idea = client.get("/api/v1/ideas/aapl")
    assert idea.status_code == 200
    assert idea.json()["recommendation"]["ticker"] == "AAPL"


def test_concurrent_run_is_rejected_with_409(client: TestClient):
    first = client.post("/api/v1/runs", json={"tickers": ["AAPL", "MSFT", "NVDA", "AMZN"]})
    assert first.status_code == 202
    run_id = first.json()["run_id"]

    second = client.post("/api/v1/runs", json={"tickers": ["JPM"]})
    if second.status_code == 202:
        # The first run finished before the second request landed; nothing to assert.
        wait_for_run(client, second.json()["run_id"])
    else:
        assert second.status_code == 409
        assert second.json()["detail"]["run_id"] == run_id
    wait_for_run(client, run_id)


def test_run_events_stream_replays_and_closes(client: TestClient):
    started = client.post("/api/v1/runs", json={"tickers": ["AAPL"]})
    run_id = started.json()["run_id"]
    wait_for_run(client, run_id)

    with client.stream("GET", f"/api/v1/runs/{run_id}/events") as stream:
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        body = "".join(stream.iter_text())
    assert "event: stage" in body
    assert body.rstrip().endswith("event: done\ndata: {}")


def test_run_list_limit_is_validated(client: TestClient):
    assert client.get("/api/v1/runs?limit=0").status_code == 422
    assert client.get("/api/v1/runs?limit=101").status_code == 422
    response = client.get("/api/v1/runs?limit=2")
    assert response.status_code == 200
    assert len(response.json()) <= 2


def test_switch_to_nse_universe(client: TestClient):
    switched = client.put("/api/v1/settings/market", json={"market_id": "in-nse"})
    assert switched.status_code == 200
    assert switched.json()["market"]["exchange_code"] == "NSE"
    universe = {row["ticker"] for row in client.get("/api/v1/universe").json()}
    assert "RELIANCE.NS" in universe
    assert "TCS.NS" in universe
    assert "AAPL" not in universe
    health = client.get("/api/v1/health").json()
    assert health["market"]["id"] == "in-nse"
    client.put("/api/v1/settings/market", json={"market_id": "us"})


def test_unknown_market_rejected(client: TestClient):
    response = client.put("/api/v1/settings/market", json={"market_id": "mars-mse"})
    assert response.status_code == 400


def test_india_desk_run_uses_inr(client: TestClient):
    client.put("/api/v1/settings/market", json={"market_id": "in-nse"})
    try:
        started = client.post("/api/v1/runs", json={"tickers": ["RELIANCE.NS", "TCS.NS"]})
        assert started.status_code == 202
        completed = wait_for_run(client, started.json()["run_id"])
        assert completed["status"] == "completed"
        assert completed["market_id"] == "in-nse"
        assert completed["summary"]["currency"] == "INR"
        assert completed["recommendations"][0]["quote"]["currency"] == "INR"
    finally:
        client.put("/api/v1/settings/market", json={"market_id": "us"})


def test_schedule_get_lists_every_market(client: TestClient):
    response = client.get("/api/v1/settings/schedule")
    assert response.status_code == 200
    body = response.json()
    ids = {row["market_id"] for row in body["markets"]}
    assert "us" in ids
    assert "in-nse" in ids
    nse = next(row for row in body["markets"] if row["market_id"] == "in-nse")
    assert nse["timezone"] == "Asia/Kolkata"
    assert nse["morning"] is None
    assert body["clock"] is False


def test_schedule_put_validates_and_persists(client: TestClient):
    bad = client.put(
        "/api/v1/settings/schedule",
        json={"markets": [{"market_id": "in-nse", "morning": "9:30", "afternoon": None}]},
    )
    assert bad.status_code == 422

    unknown = client.put(
        "/api/v1/settings/schedule",
        json={"markets": [{"market_id": "mars", "morning": "09:30", "afternoon": None}]},
    )
    assert unknown.status_code == 422

    ok = client.put(
        "/api/v1/settings/schedule",
        json={
            "markets": [
                {"market_id": "in-nse", "morning": "09:30", "afternoon": "15:45"},
                {"market_id": "us", "morning": None, "afternoon": None},
            ]
        },
    )
    assert ok.status_code == 200
    nse = next(row for row in ok.json()["markets"] if row["market_id"] == "in-nse")
    assert nse["morning"] == "09:30"
    assert nse["afternoon"] == "15:45"
    assert ok.json()["clock"] is True
    assert ok.json()["next"]
    assert ok.json()["next"][0]["market_id"] == "in-nse"

    again = client.get("/api/v1/settings/schedule").json()
    nse2 = next(row for row in again["markets"] if row["market_id"] == "in-nse")
    assert nse2["morning"] == "09:30"

    jobs = {job.id for job in client.app.state.desk_scheduler._scheduler.get_jobs()}
    assert "desk-in-nse-morning" in jobs
    assert "desk-in-nse-afternoon" in jobs

    client.put("/api/v1/settings/schedule", json={"markets": []})
    assert not client.app.state.desk_scheduler._scheduler.get_jobs()


def test_presets_and_universe_validate(client: TestClient):
    presets = client.get("/api/v1/markets/us/presets")
    assert presets.status_code == 200
    body = presets.json()
    assert body["market_id"] == "us"
    assert body["presets"]
    assert body["presets"][0]["tickers"]
    checked = client.post("/api/v1/admin/universe/validate", json={"tickers": ["AAPL", "MSFT"]})
    assert checked.status_code == 200
    assert checked.json()["verified"] is False
    assert checked.json()["tickers"][0]["status"] == "not_verified"


def test_api_key_guards_mutations(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SMP_API_KEY", "s3cret")
    get_settings.cache_clear()
    try:
        # Reads stay open.
        assert client.get("/api/v1/universe").status_code == 200
        # Writes need the key.
        denied = client.put("/api/v1/settings/appetite", json={"risk_appetite": "balanced"})
        assert denied.status_code == 401
        wrong = client.put(
            "/api/v1/settings/appetite",
            json={"risk_appetite": "balanced"},
            headers={"X-API-Key": "nope"},
        )
        assert wrong.status_code == 401
        allowed = client.put(
            "/api/v1/settings/appetite",
            json={"risk_appetite": "balanced"},
            headers={"X-API-Key": "s3cret"},
        )
        assert allowed.status_code == 200
    finally:
        monkeypatch.delenv("SMP_API_KEY", raising=False)
        get_settings.cache_clear()
