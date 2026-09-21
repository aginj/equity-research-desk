import httpx
import pytest

from app import ingest
from app.config import Settings
from app.ingest import DataHub
from app.markets import get_market


def _settings(**overrides) -> Settings:
    base = {
        "SMP_FORCE_DEMO_DATA": "false",
        "FINNHUB_API_KEY": "",
        "NEWSAPI_KEY": "",
        "ALPHAVANTAGE_API_KEY": "",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch):
    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(ingest.asyncio, "sleep", _instant)


@pytest.mark.asyncio
async def test_get_json_retries_on_429_then_succeeds(no_sleep):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"ok": True})

    hub = DataHub(_settings())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        data = await hub._get_json(client, "https://example.test/x", label="test")
    assert data == {"ok": True}
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_get_json_gives_up_after_retries(no_sleep):
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    hub = DataHub(_settings())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        data = await hub._get_json(client, "https://example.test/x", label="test", retries=2)
    assert data is None
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_get_json_does_not_retry_client_errors(no_sleep):
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403, json={"error": "premium"})

    hub = DataHub(_settings())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        data = await hub._get_json(client, "https://example.test/x", label="test")
    assert data is None
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_finnhub_key_sent_as_header_not_query(no_sleep):
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("X-Finnhub-Token", "")
        return httpx.Response(200, json={"c": 101.5, "pc": 100.0, "t": 1_700_000_000})

    hub = DataHub(_settings(FINNHUB_API_KEY="fh-secret"))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        quote = await hub._quote(client, "AAPL", get_market("us"))
    assert quote is not None
    assert quote.price == 101.5
    assert quote.change_pct == 1.5
    assert seen["token"] == "fh-secret"
    assert "fh-secret" not in seen["url"]


@pytest.mark.asyncio
async def test_load_universe_uses_requested_market_not_shared_state():
    hub = DataHub(_settings(SMP_FORCE_DEMO_DATA="true"))
    nse, us = (
        await hub.load_universe(["UNKNOWN.NS"], get_market("in-nse")),
        await hub.load_universe(["UNKNOWN"], get_market("us")),
    )
    assert nse[0].quote.currency == "INR"
    assert nse[0].profile.exchange == "NSE"
    assert us[0].quote.currency == "USD"
    assert us[0].profile.exchange == "US"


@pytest.mark.asyncio
async def test_cik_lookup_failure_is_not_cached_forever(no_sleep, monkeypatch):
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 3:  # first attempt + 2 retries all fail
            return httpx.Response(500)
        return httpx.Response(200, json={"0": {"ticker": "AAPL", "cik_str": 320193}})

    hub = DataHub(_settings())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await hub._cik_for(client, "AAPL") is None
        # Simulate the failure-retry window elapsing.
        hub._cik_loaded_at -= ingest._CIK_FAILURE_RETRY_SECONDS + 1
        assert await hub._cik_for(client, "AAPL") == "320193"
