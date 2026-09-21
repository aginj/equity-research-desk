from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import __version__
from app.agents.orchestrator import DeskOrchestrator, RunInProgressError
from app.auth import AuthUser, optional_user, require_admin, require_user
from app.config import get_settings
from app.data.demo import PROFILES
from app.db import UniverseRow
from app.domain import AnalysisResult, Book, RiskAppetite, UniverseTicker
from app.markets import (
    MARKETS,
    MarketSpec,
    catalog_payload,
    get_market,
    market_payload,
    normalize_ticker,
)
from app.ratelimit import default_rate_limit, rate_limit
from app.store import (
    SETTING_ACTIVE_MARKET,
    add_to_watchlist,
    coverage_requests,
    current_appetite,
    current_market_id,
    ensure_market_universe,
    get_engine,
    get_preferences,
    list_watchlist,
    remove_from_watchlist,
    set_appetite,
    set_preferences,
    set_setting,
    upsert_user,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", dependencies=[Depends(default_rate_limit)])
_settings = get_settings()
_limit_runs = Depends(rate_limit(_settings.rate_limit_runs, "runs"))
_limit_writes = Depends(rate_limit(_settings.rate_limit_writes, "writes"))

# Exchange symbols: letters/digits, optional venue suffix (RELIANCE.NS, BRK-B, 0005.HK, ^NSEI).
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-^=&]{0,19}$")
_SSE_HEARTBEAT_SECONDS = 15.0
HTTP_422 = 422  # starlette renamed its constant between versions; avoid the deprecation churn

_PUBLIC_RESULT = {"recommendations_raw"}


# ------------------------------------------------------------------ schemas


class RunRequest(BaseModel):
    tickers: list[str] | None = Field(default=None, max_length=500)
    risk_appetite: RiskAppetite | None = None
    market_id: str | None = Field(default=None, min_length=1, max_length=32)


class UniverseUpdate(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=500)


class AppetiteUpdate(BaseModel):
    risk_appetite: RiskAppetite


class MarketUpdate(BaseModel):
    market_id: str = Field(min_length=1, max_length=32)


class PreferencesUpdate(BaseModel):
    market_id: str | None = Field(default=None, min_length=1, max_length=32)
    risk_appetite: RiskAppetite | None = None


class WatchlistUpdate(BaseModel):
    market_id: str | None = Field(default=None, min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=500)


class UserOut(BaseModel):
    id: str
    email: str | None
    name: str | None
    image: str | None
    role: str


class PreferencesOut(BaseModel):
    market_id: str
    risk_appetite: RiskAppetite


class WatchlistItem(BaseModel):
    ticker: str
    market_id: str
    note: str | None = None
    added_at: datetime
    covered: bool
    name: str | None = None
    sector: str | None = None


class MeOut(BaseModel):
    user: UserOut
    preferences: PreferencesOut
    watchlist: list[WatchlistItem]


# ------------------------------------------------------------- dependencies


def get_orchestrator(request: Request) -> DeskOrchestrator:
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Desk is not initialized")
    return orch


def _market_or_400(market_id: str | None) -> MarketSpec:
    venue = market_id or current_market_id()
    if venue not in MARKETS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown market")
    return get_market(venue)


def _clean_tickers(raw: list[str], limit: int) -> list[str]:
    cleaned: list[str] = []
    for item in raw:
        symbol = normalize_ticker(item)
        if not symbol:
            continue
        if not _TICKER_RE.match(symbol):
            raise HTTPException(HTTP_422, f"Invalid ticker symbol: {item!r}")
        if symbol not in cleaned:
            cleaned.append(symbol)
    if not cleaned:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Universe cannot be empty")
    if len(cleaned) > limit:
        raise HTTPException(
            HTTP_422,
            f"Too many tickers ({len(cleaned)}); the limit is {limit}",
        )
    return cleaned


def _clean_ticker(raw: str) -> str:
    symbol = normalize_ticker(raw)
    if not symbol or not _TICKER_RE.match(symbol):
        raise HTTPException(HTTP_422, f"Invalid ticker symbol: {raw!r}")
    return symbol


def _universe_rows(market: MarketSpec) -> list[UniverseTicker]:
    with Session(get_engine()) as session:
        rows = session.exec(
            select(UniverseRow)
            .where(UniverseRow.market_id == market.id)
            .order_by(UniverseRow.ticker)
        ).all()
    return [
        UniverseTicker(
            ticker=r.ticker,
            name=r.name,
            sector=r.sector,
            active=r.active,
            market_id=r.market_id,
            exchange=market.exchange_code,
            currency=market.currency,
        )
        for r in rows
    ]


def _universe_index(market_id: str) -> dict[str, UniverseRow]:
    with Session(get_engine()) as session:
        rows = session.exec(select(UniverseRow).where(UniverseRow.market_id == market_id)).all()
    return {r.ticker: r for r in rows}


def _watchlist_items(user_id: str, market_id: str | None) -> list[WatchlistItem]:
    rows = list_watchlist(user_id, market_id)
    indexes: dict[str, dict[str, UniverseRow]] = {}
    items: list[WatchlistItem] = []
    for row in rows:
        index = indexes.setdefault(row.market_id, _universe_index(row.market_id))
        hit = index.get(row.ticker)
        profile = PROFILES.get(row.ticker)
        items.append(
            WatchlistItem(
                ticker=row.ticker,
                market_id=row.market_id,
                note=row.note,
                added_at=row.added_at,
                covered=bool(hit and hit.active),
                name=(hit.name if hit else None) or (profile.name if profile else None),
                sector=(hit.sector if hit else None) or (profile.sector if profile else None),
            )
        )
    return items


def _user_out(user: AuthUser) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name, image=user.image, role=user.role)


# ------------------------------------------------------------------- routes


@router.get("/health")
def health(request: Request) -> dict:
    settings = get_settings()
    db_ok = True
    try:
        market_id = current_market_id()
        appetite = current_appetite()
    except Exception:  # pragma: no cover - only on a broken database
        logger.exception("Health check: database unavailable")
        db_ok = False
        market_id = settings.default_market
        appetite = settings.risk_appetite
    orch = getattr(request.app.state, "orchestrator", None)
    return {
        "status": "ok" if db_ok else "degraded",
        "app": settings.app_name,
        "version": __version__,
        "environment": settings.environment,
        "database": "ok" if db_ok else "error",
        "llm": settings.has_llm,
        "live_market": settings.has_live_market,
        "force_demo": settings.force_demo_data,
        "auth": settings.auth_enabled,
        "risk_appetite": appetite,
        "market": market_payload(get_market(market_id)),
        "active_run_id": orch.active_run_id if orch else None,
    }


@router.get("/markets")
def markets() -> dict:
    payload = catalog_payload()
    payload["active"] = market_payload(get_market(current_market_id()))
    return payload


# --- desk defaults (admin) ------------------------------------------------------------------


@router.get("/settings/market")
def get_market_setting() -> dict:
    return {"market": market_payload(get_market(current_market_id()))}


@router.put("/settings/market", dependencies=[Depends(require_admin)])
def set_market_setting(payload: MarketUpdate) -> dict:
    if payload.market_id not in MARKETS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown market")
    set_setting(SETTING_ACTIVE_MARKET, payload.market_id)
    ensure_market_universe(payload.market_id)
    return {"market": market_payload(get_market(payload.market_id))}


@router.get("/settings/appetite")
def get_appetite() -> dict:
    return {"risk_appetite": current_appetite()}


@router.put("/settings/appetite", dependencies=[Depends(require_admin)])
def set_appetite_setting(payload: AppetiteUpdate) -> dict:
    set_appetite(payload.risk_appetite)
    return {"risk_appetite": payload.risk_appetite}


# --- universe -------------------------------------------------------------------------------


@router.get("/universe", response_model=list[UniverseTicker])
def universe(market_id: str | None = Query(default=None, max_length=32)) -> list[UniverseTicker]:
    market = _market_or_400(market_id)
    ensure_market_universe(market.id)
    return _universe_rows(market)


@router.put(
    "/universe",
    response_model=list[UniverseTicker],
    dependencies=[Depends(require_admin)],
)
def replace_universe(
    payload: UniverseUpdate,
    market_id: str | None = Query(default=None, max_length=32),
) -> list[UniverseTicker]:
    market = _market_or_400(market_id)
    tickers = _clean_tickers(payload.tickers, get_settings().max_universe_size)
    with Session(get_engine()) as session:
        existing = session.exec(select(UniverseRow).where(UniverseRow.market_id == market.id)).all()
        for row in existing:
            session.delete(row)
        for ticker in tickers:
            profile = PROFILES.get(ticker)
            session.add(
                UniverseRow(
                    market_id=market.id,
                    ticker=ticker,
                    name=profile.name if profile else ticker,
                    sector=profile.sector if profile else None,
                    active=True,
                )
            )
        session.commit()
    logger.info("Universe replaced", extra={"market": market.id, "count": len(tickers)})
    return _universe_rows(market)


# --- runs -----------------------------------------------------------------------------------


@router.post(
    "/runs",
    response_model=AnalysisResult,
    response_model_exclude=_PUBLIC_RESULT,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[_limit_runs],
)
async def start_run(
    request: Request,
    payload: RunRequest | None = None,
    admin: AuthUser = Depends(require_admin),
) -> AnalysisResult:
    body = payload or RunRequest()
    appetite = body.risk_appetite or current_appetite()
    market = _market_or_400(body.market_id)
    tickers = (
        _clean_tickers(body.tickers, get_settings().max_universe_size) if body.tickers else None
    )
    try:
        result = await get_orchestrator(request).start(
            tickers=tickers, appetite=appetite, market_id=market.id
        )
    except RunInProgressError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"message": "A desk run is already in progress", "run_id": exc.run_id},
        ) from exc
    logger.info("Run triggered", extra={"run_id": result.run_id, "by": admin.id})
    return result


@router.get("/runs", response_model=list[AnalysisResult], response_model_exclude=_PUBLIC_RESULT)
def list_runs(
    request: Request,
    limit: int = Query(default=12, ge=1, le=100),
    market_id: str | None = Query(default=None, max_length=32),
) -> list[AnalysisResult]:
    if market_id is not None and market_id not in MARKETS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown market")
    return get_orchestrator(request).list_runs(limit=limit, market_id=market_id)


@router.get("/runs/latest", response_model=AnalysisResult, response_model_exclude=_PUBLIC_RESULT)
def latest_run(
    request: Request, market_id: str | None = Query(default=None, max_length=32)
) -> AnalysisResult:
    market = _market_or_400(market_id)
    result = get_orchestrator(request).latest(market.id)
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No desk runs yet")
    return result


@router.get("/runs/{run_id}", response_model=AnalysisResult, response_model_exclude=_PUBLIC_RESULT)
def get_run(request: Request, run_id: str) -> AnalysisResult:
    result = get_orchestrator(request).get(run_id)
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return result


@router.get("/runs/{run_id}/events")
async def run_events(request: Request, run_id: str) -> StreamingResponse:
    orch = get_orchestrator(request)
    if not orch.get(run_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    queue = orch.bus.subscribe(run_id)

    async def gen() -> AsyncIterator[str]:
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_SSE_HEARTBEAT_SECONDS)
                except TimeoutError:
                    # Comment frame keeps proxies from idling out the connection and lets
                    # the server notice a disconnected client.
                    yield ": ping\n\n"
                    continue
                if event is None:
                    yield "event: done\ndata: {}\n\n"
                    break
                yield f"event: stage\ndata: {event.model_dump_json()}\n\n"
        finally:
            orch.bus.unsubscribe(run_id, queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- the book (public, viewer's appetite) ---------------------------------------------------


def _book(
    orch: DeskOrchestrator, market_id: str | None, appetite: RiskAppetite | None
) -> Book | None:
    market = _market_or_400(market_id)
    result = orch.latest(market.id)
    if not result:
        return None
    stored = result.summary.risk_appetite if result.summary else current_appetite()
    view, repoliced = (result, False) if appetite is None else orch.repolicy(result, appetite)
    return Book(run=view.public(), appetite=appetite or stored, repoliced=repoliced)


@router.get("/book", response_model=Book, response_model_exclude={"run": _PUBLIC_RESULT})
def book(
    request: Request,
    market_id: str | None = Query(default=None, max_length=32),
    appetite: RiskAppetite | None = Query(default=None),
) -> Book:
    """Latest completed run for a venue, optionally re-ranked under a viewer's appetite."""
    result = _book(get_orchestrator(request), market_id, appetite)
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No desk runs yet")
    return result


@router.get("/ideas/{ticker}")
def idea(
    request: Request,
    ticker: str,
    market_id: str | None = Query(default=None, max_length=32),
    appetite: RiskAppetite | None = Query(default=None),
) -> dict:
    symbol = normalize_ticker(ticker)
    view = _book(get_orchestrator(request), market_id, appetite)
    if not view:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No desk runs yet")
    result = view.run
    rec = next((r for r in result.recommendations if r.ticker == symbol), None)
    intel = next((i for i in result.intel if i.ticker == symbol), None)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No idea for that ticker in the latest run")
    return {
        "run_id": result.run_id,
        "appetite": view.appetite,
        "recommendation": rec.model_dump(mode="json"),
        "intel": intel.model_dump(mode="json") if intel else None,
    }


@router.get("/recommendations")
def recommendations(
    request: Request,
    market_id: str | None = Query(default=None, max_length=32),
    appetite: RiskAppetite | None = Query(default=None),
) -> dict:
    view = _book(get_orchestrator(request), market_id, appetite)
    if not view:
        return {"run_id": None, "recommendations": []}
    return {
        "run_id": view.run.run_id,
        "appetite": view.appetite,
        "recommendations": [r.model_dump(mode="json") for r in view.run.recommendations],
    }


# --- personal workspace (signed in) ---------------------------------------------------------


def _touch(user: AuthUser) -> None:
    upsert_user(user.id, email=user.email, name=user.name, image=user.image, role=user.role)


@router.get("/me", response_model=MeOut)
def me(user: AuthUser = Depends(require_user)) -> MeOut:
    _touch(user)
    prefs = get_preferences(user.id)
    return MeOut(
        user=_user_out(user),
        preferences=PreferencesOut(
            market_id=prefs.market_id,
            risk_appetite=prefs.risk_appetite,  # type: ignore[arg-type]
        ),
        watchlist=_watchlist_items(user.id, None),
    )


@router.put("/me/preferences", response_model=PreferencesOut, dependencies=[_limit_writes])
def update_preferences(
    payload: PreferencesUpdate,
    user: AuthUser = Depends(require_user),
) -> PreferencesOut:
    if payload.market_id is not None and payload.market_id not in MARKETS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown market")
    _touch(user)
    if payload.market_id:
        ensure_market_universe(payload.market_id)
    prefs = set_preferences(
        user.id, market_id=payload.market_id, risk_appetite=payload.risk_appetite
    )
    return PreferencesOut(
        market_id=prefs.market_id,
        risk_appetite=prefs.risk_appetite,  # type: ignore[arg-type]
    )


@router.get("/me/watchlist", response_model=list[WatchlistItem])
def watchlist(
    market_id: str | None = Query(default=None, max_length=32),
    user: AuthUser = Depends(require_user),
) -> list[WatchlistItem]:
    if market_id is not None and market_id not in MARKETS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown market")
    return _watchlist_items(user.id, market_id)


@router.put("/me/watchlist/{ticker}", response_model=WatchlistItem, dependencies=[_limit_writes])
def watch(
    ticker: str,
    payload: WatchlistUpdate | None = None,
    user: AuthUser = Depends(require_user),
) -> WatchlistItem:
    body = payload or WatchlistUpdate()
    symbol = _clean_ticker(ticker)
    market_id = body.market_id or get_preferences(user.id).market_id
    if market_id not in MARKETS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown market")
    _touch(user)
    if len(list_watchlist(user.id, market_id)) >= 200:
        raise HTTPException(HTTP_422, "Watchlist limit reached (200 per venue)")
    add_to_watchlist(user.id, market_id, symbol, body.note)
    return next(i for i in _watchlist_items(user.id, market_id) if i.ticker == symbol)


@router.delete(
    "/me/watchlist/{ticker}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_limit_writes],
)
def unwatch(
    ticker: str,
    market_id: str | None = Query(default=None, max_length=32),
    user: AuthUser = Depends(require_user),
) -> Response:
    symbol = _clean_ticker(ticker)
    venue = market_id or get_preferences(user.id).market_id
    if not remove_from_watchlist(user.id, venue, symbol):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not on your watchlist")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- admin ----------------------------------------------------------------------------------


@router.get("/admin/coverage-requests", dependencies=[Depends(require_admin)])
def admin_coverage_requests() -> dict:
    """Watchlisted tickers outside the analyzed universe — demand signal for admins."""
    return {"requests": coverage_requests()}


@router.get("/me/role")
def my_role(user: AuthUser | None = Depends(optional_user)) -> dict:
    """Cheap probe for the UI: who does the API think I am?"""
    return {"authenticated": user is not None, "role": user.role if user else "anonymous"}
