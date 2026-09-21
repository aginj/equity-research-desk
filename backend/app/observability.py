"""Logging setup, request correlation, and access logging.

The middleware is written against raw ASGI rather than Starlette's ``BaseHTTPMiddleware``
so that it does not buffer or interfere with the SSE streaming endpoint.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

_RESERVED_LOG_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message",
    "asctime",
}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_ATTRS and key != "request_id":
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int | str, json_mode: bool) -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    if json_mode:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s")
        )
    root.addHandler(handler)
    root.setLevel(level)
    # uvicorn's own access log duplicates ours; keep its error log.
    logging.getLogger("uvicorn.access").disabled = True
    for noisy in ("httpx", "httpcore", "openai", "apscheduler"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, root.level))


_access_log = logging.getLogger("desk.access")

SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cache-control", b"no-store"),
)


class RequestContextMiddleware:
    """Assign a request id, add security headers, and emit one access-log line per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = _header(scope, b"x-request-id")
        request_id = incoming[:64] if incoming else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                existing = {name.lower() for name, _ in headers}
                for name, value in SECURITY_HEADERS:
                    if name not in existing:
                        headers.append((name, value))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            path = scope.get("path", "")
            if path not in {"/api/v1/health", "/"}:
                _access_log.info(
                    "%s %s -> %s in %.1fms",
                    scope.get("method", "-"),
                    path,
                    status_holder["status"],
                    elapsed_ms,
                    extra={
                        "method": scope.get("method"),
                        "path": path,
                        "status": status_holder["status"],
                        "duration_ms": round(elapsed_ms, 1),
                        "client": (scope.get("client") or ("-",))[0],
                    },
                )
            request_id_ctx.reset(token)


def get_request_id(request: Any) -> str | None:
    """Request id for the current request, readable even outside the middleware's context."""
    scope_state = getattr(request, "scope", {}).get("state") or {}
    return scope_state.get("request_id") or request_id_ctx.get()


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            return value.decode("latin-1", errors="replace")
    return None
