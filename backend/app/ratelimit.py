"""Request rate limiting as FastAPI dependencies (in-memory; the API runs as one worker).

Built directly on the ``limits`` library rather than slowapi: slowapi's middleware resolves
endpoints by walking ``app.routes``, which FastAPI >= 0.141 wraps lazily, so its default
limits silently never applied. Dependencies are resolved by FastAPI itself and need no
route introspection.

* ``default_rate_limit`` is attached to the API router and keys anonymous traffic by IP.
* ``rate_limit("5/minute", "runs")`` tightens individual endpoints and keys by user id
  when a bearer token is present.
* Health probes and the SSE stream are exempt (they are long-lived or hit by orchestrators).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from limits import RateLimitItem, parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from app.auth import AuthUser, optional_user, rate_limit_key
from app.config import get_settings

logger = logging.getLogger(__name__)

_EXEMPT_SUFFIXES = ("/health", "/events")


class RateLimiter:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._storage = MemoryStorage()
        self._strategy = MovingWindowRateLimiter(self._storage)
        self._items: dict[str, RateLimitItem] = {}

    def reset(self) -> None:
        self._storage.reset()

    def _item(self, limit: str) -> RateLimitItem:
        item = self._items.get(limit)
        if item is None:
            item = self._items[limit] = parse(limit)
        return item

    def hit(self, request: Request, limit: str, scope: str) -> None:
        """Count one request against ``limit`` for the caller; raise 429 when exhausted."""
        if not self.enabled:
            return
        item = self._item(limit)
        key = rate_limit_key(request)
        if self._strategy.hit(item, scope, key):
            return
        stats = self._strategy.get_window_stats(item, scope, key)
        retry_after = max(1, int(stats.reset_time - time.time()))
        logger.info("Rate limited %s on %s (%s)", key, scope, limit)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Rate limit exceeded ({limit}). Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(item.amount)},
        )


_settings = get_settings()
limiter = RateLimiter(enabled=_settings.rate_limit_enabled)


def default_rate_limit(request: Request) -> None:
    """Router-wide limit for everything except health and event streams."""
    if request.url.path.endswith(_EXEMPT_SUFFIXES):
        return
    limiter.hit(request, _settings.rate_limit_default, "default")


def rate_limit(limit: str, scope: str) -> Callable[..., None]:
    """Per-endpoint limit, keyed by the signed-in user when there is one."""

    def dependency(request: Request, _user: AuthUser | None = Depends(optional_user)) -> None:
        limiter.hit(request, limit, scope)

    return dependency
