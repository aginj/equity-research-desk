"""Desk orchestrator — sequential specialists, then policy. Emits run events for the UI."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import OrderedDict, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime

from sqlmodel import Session, col, select

from app.agents.chief import ChiefAnalyst
from app.agents.llm import LLMClient
from app.agents.scoring import build_scorecard
from app.agents.specialists import FilingsAnalyst, NewsAnalyst
from app.config import Settings, get_settings
from app.db import AnalysisRunRow, UniverseRow
from app.domain import (
    AnalysisResult,
    DeskSummary,
    Recommendation,
    RiskAppetite,
    RunEvent,
    RunStage,
    TickerIntel,
)
from app.ingest import DataHub
from app.markets import MarketSpec, get_market
from app.policy import apply_policy
from app.store import current_market_id, prune_run_history

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


class RunInProgressError(RuntimeError):
    """Raised when a desk run is requested while another one is still executing."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Desk run {run_id} is already in progress")
        self.run_id = run_id


class RunBus:
    """In-process pub/sub for run events with bounded replay history.

    The bus lives in a single worker process; run the API with one uvicorn worker.
    """

    def __init__(self, max_runs: int = 64) -> None:
        self._max_runs = max_runs
        self._queues: dict[str, list[asyncio.Queue[RunEvent | None]]] = defaultdict(list)
        self._history: OrderedDict[str, list[RunEvent]] = OrderedDict()
        self._closed: set[str] = set()

    def subscribe(self, run_id: str) -> asyncio.Queue[RunEvent | None]:
        queue: asyncio.Queue[RunEvent | None] = asyncio.Queue()
        for event in self._history.get(run_id, []):
            queue.put_nowait(event)
        if run_id in self._closed or run_id not in self._history:
            # Either finished, or unknown to this process (e.g. persisted before a restart).
            queue.put_nowait(None)
        else:
            self._queues[run_id].append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[RunEvent | None]) -> None:
        listeners = self._queues.get(run_id)
        if listeners and queue in listeners:
            listeners.remove(queue)
            if not listeners:
                self._queues.pop(run_id, None)

    def open(self, run_id: str) -> None:
        self._history[run_id] = []
        self._history.move_to_end(run_id)
        self._evict()

    async def publish(self, event: RunEvent) -> None:
        self._history.setdefault(event.run_id, []).append(event)
        for queue in list(self._queues.get(event.run_id) or []):
            await queue.put(event)

    async def close(self, run_id: str) -> None:
        self._closed.add(run_id)
        for queue in list(self._queues.get(run_id) or []):
            await queue.put(None)
        self._queues.pop(run_id, None)

    def _evict(self) -> None:
        while len(self._history) > self._max_runs:
            oldest, _ = self._history.popitem(last=False)
            self._closed.discard(oldest)
            self._queues.pop(oldest, None)


class DeskOrchestrator:
    def __init__(
        self,
        session_factory: SessionFactory,
        settings: Settings | None = None,
        bus: RunBus | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        self.bus = bus or RunBus()
        self.llm = LLMClient(self.settings)
        self.hub = DataHub(self.settings)
        self.news = NewsAnalyst(self.llm)
        self.filings = FilingsAnalyst(self.llm)
        self.chief = ChiefAnalyst(self.llm)
        self._lock = asyncio.Lock()
        self._active_run_id: str | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------ queries

    @property
    def active_run_id(self) -> str | None:
        return self._active_run_id

    def latest(self, market_id: str | None = None) -> AnalysisResult | None:
        """Most recent *completed* run for the venue. Failed runs never replace a good book."""
        venue = market_id or current_market_id()
        with self.session_factory() as session:
            row = session.exec(
                select(AnalysisRunRow)
                .where(
                    AnalysisRunRow.market_id == venue,
                    AnalysisRunRow.status == "completed",
                    col(AnalysisRunRow.payload_json).is_not(None),
                )
                .order_by(col(AnalysisRunRow.started_at).desc())
                .limit(1)
            ).first()
        return _row_to_result(row) if row else None

    def get(self, run_id: str) -> AnalysisResult | None:
        with self.session_factory() as session:
            row = session.get(AnalysisRunRow, run_id)
        return _row_to_result(row) if row else None

    def list_runs(self, limit: int = 12, market_id: str | None = None) -> list[AnalysisResult]:
        with self.session_factory() as session:
            query = select(AnalysisRunRow)
            if market_id:
                query = query.where(AnalysisRunRow.market_id == market_id)
            rows = session.exec(
                query.order_by(col(AnalysisRunRow.started_at).desc()).limit(limit)
            ).all()
        return [_row_to_result(row) for row in rows]

    def repolicy(
        self, result: AnalysisResult, appetite: RiskAppetite
    ) -> tuple[AnalysisResult, bool]:
        """View a completed run under a different appetite.

        Policy is deterministic, so re-applying it to the chief analyst's raw output gives
        exactly the book that appetite would have produced — no agents, no vendor calls.
        Returns ``(result, repoliced)``; older runs without raw output are returned as-is.
        """
        stored = result.summary.risk_appetite if result.summary else None
        if not result.recommendations_raw or stored == appetite:
            return result, False
        market = get_market(result.market_id)
        recs = apply_policy(
            [r.model_copy(deep=True) for r in result.recommendations_raw], appetite, market
        )
        llm_enabled = result.summary.llm_enabled if result.summary else self.llm.enabled
        summary = _summarize(result.intel, recs, appetite, self.settings, llm_enabled, market)
        return result.model_copy(update={"recommendations": recs, "summary": summary}), True

    # ----------------------------------------------------------------- lifecycle

    async def start(
        self,
        tickers: list[str] | None = None,
        appetite: RiskAppetite | None = None,
        market_id: str | None = None,
    ) -> AnalysisResult:
        async with self._lock:
            if self._active_run_id is not None:
                raise RunInProgressError(self._active_run_id)

            run_id = uuid.uuid4().hex[:12]
            started = datetime.now(UTC)
            risk: RiskAppetite = appetite or self.settings.risk_appetite
            market = get_market(market_id or current_market_id())
            names = tickers or self._universe(market.id)
            stub = AnalysisResult(
                run_id=run_id,
                status="running",
                stage="queued",
                started_at=started,
                market_id=market.id,
            )
            with self.session_factory() as session:
                session.add(
                    AnalysisRunRow(
                        id=run_id,
                        status="running",
                        stage="queued",
                        risk_appetite=risk,
                        market_id=market.id,
                        started_at=started,
                    )
                )
                session.commit()

            self._active_run_id = run_id
            self.bus.open(run_id)
            task = asyncio.create_task(
                self._execute(stub, names, risk, market), name=f"desk-run-{run_id}"
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            logger.info(
                "Desk run started",
                extra={"run_id": run_id, "market": market.id, "tickers": len(names)},
            )
            return stub

    async def shutdown(self, grace_seconds: float = 5.0) -> None:
        """Cancel in-flight runs and mark them failed so no row is left 'running' forever."""
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=grace_seconds)

    def _universe(self, market_id: str) -> list[str]:
        with self.session_factory() as session:
            rows = session.exec(
                select(UniverseRow).where(
                    UniverseRow.market_id == market_id,
                    col(UniverseRow.active).is_(True),
                )
            ).all()
        if rows:
            return [r.ticker for r in rows]
        return list(get_market(market_id).default_universe)

    async def _execute(
        self,
        stub: AnalysisResult,
        tickers: list[str],
        appetite: RiskAppetite,
        market: MarketSpec,
    ) -> None:
        run_id = stub.run_id
        try:
            filings_label = market.filings_label
            await self._emit(
                run_id,
                "ingest",
                f"Collecting news, quotes, and {filings_label} for {market.label}.",
                0.08,
            )
            bundle = await self.hub.load_universe(tickers, market)

            await self._emit(
                run_id, "news_analyst", "News analyst extracting material events.", 0.28
            )
            bundle = [await self.news.run(item) for item in bundle]

            await self._emit(
                run_id, "filings_analyst", f"Filings analyst reading {filings_label}.", 0.46
            )
            bundle = [await self.filings.run(item) for item in bundle]

            await self._emit(
                run_id,
                "fundamentals_analyst",
                "Scoring quality, valuation, and momentum.",
                0.62,
            )
            scored: list[TickerIntel] = []
            for item in bundle:
                card = build_scorecard(item)
                scored.append(item.model_copy(update={"scorecard": card}))

            await self._emit(
                run_id,
                "risk_analyst",
                "Risk analyst tagging event and factor exposure.",
                0.72,
            )

            await self._emit(
                run_id,
                "chief_analyst",
                "Chief analyst drafting sourced recommendations.",
                0.84,
            )
            recs: list[Recommendation] = []
            for item in scored:
                recs.append(await self.chief.run(item))

            await self._emit(
                run_id, "policy", f"Applying {market.exchange_code} desk policy.", 0.93
            )
            raw = [r.model_copy(deep=True) for r in recs]
            recs = apply_policy(recs, appetite, market)

            summary = _summarize(scored, recs, appetite, self.settings, self.llm.enabled, market)
            finished = datetime.now(UTC)
            result = AnalysisResult(
                run_id=run_id,
                status="completed",
                stage="completed",
                started_at=stub.started_at,
                finished_at=finished,
                market_id=market.id,
                summary=summary,
                recommendations=recs,
                intel=scored,
                recommendations_raw=raw,
            )
            await asyncio.to_thread(self._persist, result)
            await self._emit(run_id, "completed", "Desk run complete.", 1.0)
            logger.info(
                "Desk run completed",
                extra={
                    "run_id": run_id,
                    "duration_s": round((finished - stub.started_at).total_seconds(), 2),
                    "accumulate": sum(1 for r in recs if r.action == "accumulate"),
                },
            )
        except asyncio.CancelledError:
            logger.warning("Desk run cancelled", extra={"run_id": run_id})
            self._persist(_failed(stub, market, "Run cancelled during shutdown"))
            raise
        except Exception as exc:
            logger.exception("Desk run failed", extra={"run_id": run_id})
            await asyncio.to_thread(self._persist, _failed(stub, market, str(exc)))
            await self._emit(run_id, "failed", f"Run failed: {exc}", 1.0)
        finally:
            if self._active_run_id == run_id:
                self._active_run_id = None
            await self.bus.close(run_id)
            try:
                await asyncio.to_thread(prune_run_history, self.settings.run_history_limit)
            except Exception:  # pragma: no cover - housekeeping must never break a run
                logger.exception("Run history pruning failed")

    def _persist(self, result: AnalysisResult) -> None:
        with self.session_factory() as session:
            row = session.get(AnalysisRunRow, result.run_id)
            if not row:
                return
            row.status = result.status
            row.stage = result.stage
            row.finished_at = result.finished_at
            row.error = result.error
            row.market_id = result.market_id
            row.payload_json = result.model_dump_json()
            session.add(row)
            session.commit()

    async def _emit(self, run_id: str, stage: RunStage, message: str, progress: float) -> None:
        event = RunEvent(
            run_id=run_id,
            stage=stage,
            message=message,
            at=datetime.now(UTC),
            progress=progress,
        )
        await asyncio.to_thread(self._update_stage, run_id, stage)
        await self.bus.publish(event)

    def _update_stage(self, run_id: str, stage: RunStage) -> None:
        with self.session_factory() as session:
            row = session.get(AnalysisRunRow, run_id)
            if row:
                row.stage = stage
                session.add(row)
                session.commit()


def _failed(stub: AnalysisResult, market: MarketSpec, error: str) -> AnalysisResult:
    return AnalysisResult(
        run_id=stub.run_id,
        status="failed",
        stage="failed",
        started_at=stub.started_at,
        finished_at=datetime.now(UTC),
        market_id=market.id,
        error=error[:2000],
    )


def _row_to_result(row: AnalysisRunRow) -> AnalysisResult:
    if row.payload_json:
        try:
            return AnalysisResult.model_validate_json(row.payload_json)
        except ValueError:
            logger.warning("Corrupt run payload; returning metadata only", extra={"run_id": row.id})
    return AnalysisResult(
        run_id=row.id,
        status=row.status,  # type: ignore[arg-type]
        stage=row.stage,  # type: ignore[arg-type]
        started_at=row.started_at,
        finished_at=row.finished_at,
        error=row.error,
        market_id=row.market_id or "us",
    )


def _summarize(
    intel: list[TickerIntel],
    recs: list[Recommendation],
    appetite: RiskAppetite,
    settings: Settings,
    llm_enabled: bool,
    market: MarketSpec,
) -> DeskSummary:
    acc = [r for r in recs if r.action == "accumulate"]
    reduce = [r for r in recs if r.action in {"reduce", "avoid"}]
    if acc:
        headline = (
            f"{len(acc)} accumulate idea{'s' if len(acc) != 1 else ''} after policy: "
            + ", ".join(r.ticker for r in acc[:4])
        )
    else:
        headline = "No accumulate ratings cleared desk policy this run."

    bias = sum(i.news_bias for i in intel) / max(len(intel), 1)
    if bias > 0.12:
        regime = "Risk-on tape in the news window, still capped by valuation and event risk."
    elif bias < -0.12:
        regime = "Defensive tape: headlines skew cautious across the book."
    else:
        regime = "Mixed tape: stock-specific stories dominate over a single factor regime."

    caveats = [
        "Research output only — not personalized investment advice and not an offer to buy "
        "or sell securities.",
        "News is lagged and often already in the price. Do not treat headlines as alpha.",
        "Recommendations are ranked inside the configured universe, not versus the entire market.",
        f"Active venue: {market.label}. Prices are in {market.currency}.",
    ]
    if market.filings != "edgar":
        caveats.append(
            f"{market.filings_label} are not pulled from a regulator feed in this build — "
            "lean on news and exchange disclosures."
        )
    if not settings.has_live_market or settings.force_demo_data:
        caveats.append(
            "Market/news feeds are partially or fully demo fixtures until API keys are configured."
        )
    if not llm_enabled:
        caveats.append("No LLM key configured — qualitative write-ups used transparent heuristics.")

    news_count = sum(len(i.news) for i in intel)
    filing_count = sum(len(i.filings) for i in intel)
    body = (
        f"{regime} {len(intel)} names analyzed, {news_count} headlines, "
        f"{filing_count} filings. "
        f"{len(reduce)} names rated reduce/avoid. Appetite: {appetite}."
    )
    return DeskSummary(
        regime=regime,
        headline=headline,
        body=body,
        risk_appetite=appetite,
        tickers_analyzed=len(intel),
        news_items=news_count,
        filings=filing_count,
        llm_enabled=llm_enabled,
        live_market=settings.has_live_market and not settings.force_demo_data,
        market_id=market.id,
        market_label=market.label,
        country=market.country,
        exchange=market.exchange,
        currency=market.currency,
        caveats=caveats,
    )
