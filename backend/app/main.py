from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.agents.orchestrator import DeskOrchestrator
from app.api import router
from app.auth import auth_enforced
from app.config import get_settings
from app.observability import RequestContextMiddleware, configure_logging, get_request_id
from app.scheduler import DeskScheduler
from app.store import init_db, recover_stale_runs, session_factory

logger = logging.getLogger("desk")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    init_db()
    recover_stale_runs()
    orchestrator = DeskOrchestrator(session_factory, settings)
    app.state.orchestrator = orchestrator
    desk_scheduler = DeskScheduler(orchestrator, interval_hours=settings.scheduler_hours)
    desk_scheduler.start()
    app.state.desk_scheduler = desk_scheduler

    if not auth_enforced(settings):
        logger.warning(
            "No SMP_AUTH_JWT_SECRET, SMP_API_KEY, or local accounts: admin endpoints are OPEN. "
            "Create an account at /signin (first user is admin) before exposing this instance."
        )
    logger.info(
        "%s %s ready - env=%s llm=%s live_market=%s demo=%s auth=%s api_key=%s admins=%d",
        settings.app_name,
        __version__,
        settings.environment,
        settings.has_llm,
        settings.has_live_market,
        settings.force_demo_data,
        auth_enforced(settings),
        settings.requires_api_key,
        len(settings.admin_email_set),
    )
    try:
        yield
    finally:
        if desk_scheduler:
            desk_scheduler.shutdown()
        await orchestrator.shutdown()
        logger.info("%s stopped", settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level_int, settings.log_json)

    application = FastAPI(
        title=settings.app_name,
        description="Agentic equity research desk. Research only — not investment advice.",
        version=__version__,
        lifespan=lifespan,
    )

    # Order matters: the outermost middleware (added last) runs first.
    application.add_middleware(GZipMiddleware, minimum_size=1024)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After", "X-RateLimit-Limit"],
        max_age=600,
    )
    application.add_middleware(RequestContextMiddleware)
    application.include_router(router)

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "request_id": get_request_id(request)},
            headers=getattr(exc, "headers", None),
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "request_id": get_request_id(request)},
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Runs in Starlette's outermost ServerErrorMiddleware, after our context var is reset,
        # so the id is read from the scope instead.
        request_id = get_request_id(request)
        logger.error(
            "Unhandled error on %s %s [%s]",
            request.method,
            request.url.path,
            request_id,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )

    @application.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "app": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "health": "/api/v1/health",
            "disclaimer": "Research only. Not investment advice.",
        }

    return application


app = create_app()
