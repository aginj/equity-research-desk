"""Bearer-token auth, roles, personal workspace, and the per-appetite book."""

from __future__ import annotations

import time
from collections.abc import Iterator

import jwt
import pytest
from fastapi.testclient import TestClient

from app.auth import TOKEN_AUDIENCE, TOKEN_ISSUER
from app.config import get_settings
from tests.conftest import wait_for_run

SECRET = "unit-test-secret-that-is-at-least-32-characters-long"
ADMIN_EMAIL = "admin@example.com"


def mint(sub: str, email: str, *, exp_offset: int = 3600, secret: str = SECRET, **extra) -> str:
    now = int(time.time())
    claims = {
        "sub": sub,
        "email": email,
        "name": email.split("@")[0].title(),
        "aud": TOKEN_AUDIENCE,
        "iss": TOKEN_ISSUER,
        "iat": now,
        "exp": now + exp_offset,
        **extra,
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("SMP_AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("SMP_ADMIN_EMAILS", f" {ADMIN_EMAIL.upper()} , other-admin@example.com")
    get_settings.cache_clear()
    try:
        yield
    finally:
        monkeypatch.delenv("SMP_AUTH_JWT_SECRET", raising=False)
        monkeypatch.delenv("SMP_ADMIN_EMAILS", raising=False)
        get_settings.cache_clear()


USER = mint("user-1", "alice@example.com")
OTHER = mint("user-2", "bob@example.com")
ADMIN = mint("admin-1", ADMIN_EMAIL)


# ------------------------------------------------------------------ token handling


def test_anonymous_can_read_but_not_use_workspace(client: TestClient, auth_env: None):
    assert client.get("/api/v1/universe").status_code == 200
    assert client.get("/api/v1/me").status_code == 401
    probe = client.get("/api/v1/me/role").json()
    assert probe == {"authenticated": False, "role": "anonymous"}


def test_invalid_tokens_are_rejected_not_downgraded(client: TestClient, auth_env: None):
    assert client.get("/api/v1/me", headers={"Authorization": "Token abc"}).status_code == 401
    forged = mint("user-1", "alice@example.com", secret="wrong-secret-wrong-secret-wrong-secret")
    assert client.get("/api/v1/me", headers=bearer(forged)).status_code == 401
    expired = mint("user-1", "alice@example.com", exp_offset=-3600)
    response = client.get("/api/v1/me", headers=bearer(expired))
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()
    # Even a read-only endpoint refuses a bad token so the UI can prompt to re-authenticate.
    assert client.get("/api/v1/me/role", headers=bearer(forged)).status_code == 401


def test_wrong_audience_is_rejected(client: TestClient, auth_env: None):
    token = jwt.encode(
        {
            "sub": "x",
            "aud": "someone-else",
            "iss": TOKEN_ISSUER,
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
        },
        SECRET,
        algorithm="HS256",
    )
    assert client.get("/api/v1/me", headers=bearer(token)).status_code == 401


def test_role_comes_from_server_allowlist_not_token(client: TestClient, auth_env: None):
    # A user token claiming role=admin is still a plain user.
    sneaky = mint("user-9", "mallory@example.com", role="admin")
    assert client.get("/api/v1/me/role", headers=bearer(sneaky)).json()["role"] == "user"
    # Allowlisted email (case-insensitive) is admin.
    assert client.get("/api/v1/me/role", headers=bearer(ADMIN)).json()["role"] == "admin"


# ------------------------------------------------------------------ admin gates


def test_mutations_require_admin(client: TestClient, auth_env: None):
    body = {"risk_appetite": "balanced"}
    assert client.put("/api/v1/settings/appetite", json=body).status_code == 401
    assert (
        client.put("/api/v1/settings/appetite", json=body, headers=bearer(USER)).status_code == 403
    )
    assert (
        client.put("/api/v1/settings/appetite", json=body, headers=bearer(ADMIN)).status_code == 200
    )
    assert client.post("/api/v1/runs", json={}, headers=bearer(USER)).status_code == 403
    assert client.get("/api/v1/admin/coverage-requests", headers=bearer(USER)).status_code == 403
    assert client.get("/api/v1/admin/coverage-requests", headers=bearer(ADMIN)).status_code == 200


def test_api_key_still_works_as_machine_admin(
    client: TestClient, auth_env: None, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SMP_API_KEY", "machine-secret")
    get_settings.cache_clear()
    try:
        ok = client.put(
            "/api/v1/settings/appetite",
            json={"risk_appetite": "balanced"},
            headers={"X-API-Key": "machine-secret"},
        )
        assert ok.status_code == 200
        bad = client.put(
            "/api/v1/settings/appetite",
            json={"risk_appetite": "balanced"},
            headers={"X-API-Key": "nope"},
        )
        assert bad.status_code == 401
    finally:
        monkeypatch.delenv("SMP_API_KEY", raising=False)
        get_settings.cache_clear()


def test_production_refuses_to_boot_without_auth(monkeypatch: pytest.MonkeyPatch):
    from app.config import Settings

    monkeypatch.setenv("SMP_ENVIRONMENT", "production")
    monkeypatch.setenv("SMP_CORS_ORIGINS", "https://desk.example.com")
    monkeypatch.setenv("SMP_AUTH_JWT_SECRET", "")
    monkeypatch.setenv("SMP_API_KEY", "")
    with pytest.raises(ValueError, match="SMP_AUTH_JWT_SECRET"):
        Settings()
    monkeypatch.setenv("SMP_AUTH_JWT_SECRET", "too-short")
    with pytest.raises(ValueError, match="32 characters"):
        Settings()
    monkeypatch.setenv("SMP_AUTH_JWT_SECRET", SECRET)
    assert Settings().auth_enabled is True


# ------------------------------------------------------------------ workspace


def test_me_creates_profile_with_desk_defaults(client: TestClient, auth_env: None):
    response = client.get("/api/v1/me", headers=bearer(USER))
    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {
        "id": "user-1",
        "email": "alice@example.com",
        "name": "Alice",
        "image": None,
        "role": "user",
    }
    assert body["preferences"]["market_id"] in {"us", "in-nse"}
    assert body["preferences"]["risk_appetite"] in {"conservative", "balanced", "aggressive"}
    assert body["watchlist"] == []


def test_preferences_are_per_user(client: TestClient, auth_env: None):
    saved = client.put(
        "/api/v1/me/preferences",
        json={"market_id": "in-nse", "risk_appetite": "conservative"},
        headers=bearer(USER),
    )
    assert saved.status_code == 200
    assert saved.json() == {"market_id": "in-nse", "risk_appetite": "conservative"}
    other = client.get("/api/v1/me", headers=bearer(OTHER)).json()["preferences"]
    assert other["risk_appetite"] != "conservative" or other["market_id"] != "in-nse"
    bad = client.put("/api/v1/me/preferences", json={"market_id": "mars"}, headers=bearer(USER))
    assert bad.status_code == 400
    # Reset so later tests see the default venue.
    client.put(
        "/api/v1/me/preferences",
        json={"market_id": "us", "risk_appetite": "balanced"},
        headers=bearer(USER),
    )


def test_watchlist_is_isolated_between_users(client: TestClient, auth_env: None):
    added = client.put(
        "/api/v1/me/watchlist/aapl",
        json={"market_id": "us", "note": "core holding"},
        headers=bearer(USER),
    )
    assert added.status_code == 200
    item = added.json()
    assert item["ticker"] == "AAPL"
    assert item["note"] == "core holding"
    assert item["covered"] is True  # AAPL is in the seeded US universe

    # Not in coverage: still allowed, flagged, and surfaces to admins as demand.
    rare = client.put("/api/v1/me/watchlist/ZZZZ", json={"market_id": "us"}, headers=bearer(USER))
    assert rare.status_code == 200
    assert rare.json()["covered"] is False

    mine = client.get("/api/v1/me/watchlist?market_id=us", headers=bearer(USER)).json()
    assert {i["ticker"] for i in mine} == {"AAPL", "ZZZZ"}
    theirs = client.get("/api/v1/me/watchlist?market_id=us", headers=bearer(OTHER)).json()
    assert theirs == []

    demand = client.get("/api/v1/admin/coverage-requests", headers=bearer(ADMIN)).json()["requests"]
    assert {"market_id": "us", "ticker": "ZZZZ", "requests": 1} in demand

    assert client.put("/api/v1/me/watchlist/bad ticker!", headers=bearer(USER)).status_code == 422
    assert (
        client.delete("/api/v1/me/watchlist/AAPL?market_id=us", headers=bearer(USER)).status_code
        == 204
    )
    assert (
        client.delete("/api/v1/me/watchlist/AAPL?market_id=us", headers=bearer(USER)).status_code
        == 404
    )
    client.delete("/api/v1/me/watchlist/ZZZZ?market_id=us", headers=bearer(USER))


# ------------------------------------------------------------------ book & re-policy


def test_book_applies_viewer_appetite_without_new_run(client: TestClient, auth_env: None):
    started = client.post(
        "/api/v1/runs",
        json={"risk_appetite": "balanced", "market_id": "us"},
        headers=bearer(ADMIN),
    )
    assert started.status_code == 202, started.text
    run = wait_for_run(client, started.json()["run_id"])
    assert run["status"] == "completed"
    assert "recommendations_raw" not in run  # never leaks through the API

    stored = client.get("/api/v1/book?market_id=us").json()
    assert stored["appetite"] == "balanced"
    assert stored["repoliced"] is False
    assert stored["run"]["run_id"] == run["run_id"]

    conservative = client.get("/api/v1/book?market_id=us&appetite=conservative").json()
    aggressive = client.get("/api/v1/book?market_id=us&appetite=aggressive").json()
    assert conservative["repoliced"] is True and aggressive["repoliced"] is True
    assert conservative["run"]["summary"]["risk_appetite"] == "conservative"
    assert aggressive["run"]["summary"]["risk_appetite"] == "aggressive"

    def accumulate(book: dict) -> int:
        return sum(1 for r in book["run"]["recommendations"] if r["action"] == "accumulate")

    # Tighter policy can only shrink the accumulate book; looser can only grow it.
    assert accumulate(conservative) <= accumulate(stored) <= accumulate(aggressive)
    # Same universe either way; nothing was re-fetched.
    assert len(conservative["run"]["recommendations"]) == len(stored["run"]["recommendations"])
    assert client.get("/api/v1/runs?market_id=us").status_code == 200
    assert client.get("/api/v1/runs?market_id=nowhere").status_code == 400

    # Idea pages honour the viewer's appetite too.
    ticker = stored["run"]["recommendations"][0]["ticker"]
    idea = client.get(f"/api/v1/ideas/{ticker}?market_id=us&appetite=conservative").json()
    assert idea["appetite"] == "conservative"
    assert idea["recommendation"]["ticker"] == ticker


# ------------------------------------------------------------------ rate limiting


def test_rate_limit_returns_429_with_retry_after(client: TestClient):
    from app.ratelimit import limiter

    limiter.enabled = True
    try:
        limiter.reset()
        statuses = [client.get("/api/v1/markets").status_code for _ in range(121)]
        assert statuses[:120] == [200] * 120
        last = client.get("/api/v1/markets")
        assert last.status_code == 429
        assert int(last.headers["retry-after"]) >= 1
        assert last.headers["x-ratelimit-limit"] == "120"
        assert "request_id" in last.json()
        # Exempt endpoints keep answering while the caller is throttled.
        assert client.get("/api/v1/health").status_code == 200
    finally:
        limiter.enabled = False
        limiter.reset()


def test_run_trigger_has_its_own_tight_limit(client: TestClient, auth_env: None):
    from app.ratelimit import limiter

    limiter.enabled = True
    try:
        limiter.reset()
        # Five attempts per minute per admin; a 409 (busy) still counts as an attempt.
        codes = [
            client.post("/api/v1/runs", json={}, headers=bearer(ADMIN)).status_code
            for _ in range(6)
        ]
        assert codes[-1] == 429
        assert all(code in {202, 409} for code in codes[:-1])
    finally:
        limiter.enabled = False
        limiter.reset()
        # Let the run that was started drain so later tests see a quiet desk.
        active = client.get("/api/v1/health").json().get("active_run_id")
        if active:
            wait_for_run(client, active)
