import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_TEST_DB = Path(__file__).resolve().parents[1] / "data" / "test.db"

os.environ.setdefault("SMP_FORCE_DEMO_DATA", "true")
os.environ.setdefault("SMP_DATABASE_URL", "sqlite:///./data/test.db")
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["CURSOR_API_KEY"] = ""
os.environ["FINNHUB_API_KEY"] = ""
os.environ["NEWSAPI_KEY"] = ""
os.environ["SMP_API_KEY"] = ""
os.environ["SMP_AUTH_JWT_SECRET"] = ""
os.environ["SMP_ADMIN_EMAILS"] = ""
# The in-memory limiter would trip on a fast test suite; test_auth toggles it explicitly.
os.environ["SMP_RATE_LIMIT_ENABLED"] = "false"

# Start every session from an empty desk so state from an aborted run cannot leak in.
for suffix in ("", "-wal", "-shm", "-journal"):
    stale = _TEST_DB.with_name(_TEST_DB.name + suffix)
    if stale.exists():
        stale.unlink()

from app.config import get_settings  # noqa: E402  (env must be set before import)

get_settings.cache_clear()


@pytest.fixture
def client():
    from app.main import app

    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def wait_for_run(client: TestClient, run_id: str, timeout_s: float = 20.0) -> dict:
    """Poll a run until it reaches a terminal state."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"completed", "failed"}:
            return body
        time.sleep(0.1)
    raise AssertionError(f"run {run_id} did not finish within {timeout_s}s")
