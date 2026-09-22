"""In-process APScheduler: weekday clock times per venue, queued so only one run executes."""

from __future__ import annotations

import asyncio
import logging

from app.agents.orchestrator import DeskOrchestrator, RunInProgressError
from app.markets import get_market
from app.schedule import SLOTS, has_clock_jobs, is_closed, parse_hhmm
from app.store import get_market_schedule, record_schedule_fire

logger = logging.getLogger(__name__)

_CRON_WEEKDAYS = "mon-fri"


class DeskScheduler:
    def __init__(self, orchestrator: DeskOrchestrator, interval_hours: int = 0) -> None:
        self.orchestrator = orchestrator
        self.interval_hours = interval_hours
        self._scheduler = None
        self._queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None

    def start(self) -> None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        if self._scheduler is not None:
            return
        self._scheduler = AsyncIOScheduler()
        self.reload()
        self._scheduler.start()
        self._worker = asyncio.create_task(self._drain(), name="desk-schedule-queue")

    def reload(self) -> None:
        """Replace jobs from the stored admin schedule (and interval fallback)."""
        if self._scheduler is None:
            return
        self._scheduler.remove_all_jobs()
        store = get_market_schedule()
        clock = has_clock_jobs(store)
        if clock:
            self._add_clock_jobs(store)
            logger.info("Clock schedule loaded")
        elif self.interval_hours > 0:
            self._scheduler.add_job(
                self.enqueue,
                "interval",
                hours=self.interval_hours,
                kwargs={"market_id": None, "slot": "interval"},
                id="desk-interval",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=600,
            )
            logger.info("Interval schedule every %s hour(s)", self.interval_hours)

    def _add_clock_jobs(self, store: dict[str, dict]) -> None:
        from zoneinfo import ZoneInfo

        from apscheduler.triggers.cron import CronTrigger

        for market_id, times in store.items():
            if not times.get("enabled", True):
                continue
            spec = get_market(market_id)
            tz = ZoneInfo(spec.timezone)
            for slot in SLOTS:
                parsed = parse_hhmm(times.get(slot) if isinstance(times.get(slot), str) else None)
                if not parsed:
                    continue
                hour, minute = parsed
                self._scheduler.add_job(
                    self.enqueue,
                    CronTrigger(
                        day_of_week=_CRON_WEEKDAYS,
                        hour=hour,
                        minute=minute,
                        timezone=tz,
                    ),
                    kwargs={"market_id": market_id, "slot": slot},
                    id=f"desk-{market_id}-{slot}",
                    replace_existing=True,
                    coalesce=True,
                    max_instances=1,
                    misfire_grace_time=600,
                )

    async def enqueue(self, market_id: str | None = None, slot: str = "interval") -> None:
        await self._queue.put((market_id or "", slot or "interval"))

    async def _drain(self) -> None:
        while True:
            market_id, slot = await self._queue.get()
            venue = market_id or None
            try:
                await self._run_when_idle(venue, slot)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Scheduled desk run failed", extra={"market": venue})
                try:
                    from app.notifications import notify_run_failed

                    notify_run_failed(
                        market_id=venue or "us",
                        run_id=None,
                        error=str(exc),
                    )
                except Exception:  # pragma: no cover
                    logger.exception("Failed to record schedule failure notification")
            finally:
                self._queue.task_done()

    async def _run_when_idle(self, market_id: str | None, slot: str) -> None:
        store = get_market_schedule()
        if market_id and is_closed(store, market_id):
            logger.info("Skipping scheduled run (paused or closed)", extra={"market": market_id})
            record_schedule_fire(market_id, slot, run_id=None, status="skipped")
            return
        while self.orchestrator.active_run_id is not None:  # noqa: ASYNC110
            await asyncio.sleep(2)
        trigger = f"schedule:{market_id}:{slot}" if market_id else "interval"
        try:
            result = await self.orchestrator.start(market_id=market_id, trigger=trigger)
        except RunInProgressError:
            await asyncio.sleep(2)
            await self._run_when_idle(market_id, slot)
            return
        logger.info(
            "Scheduled run started",
            extra={"run_id": result.run_id, "market": result.market_id},
        )
        while self.orchestrator.active_run_id == result.run_id:  # noqa: ASYNC110
            await asyncio.sleep(2)
        finished = self.orchestrator.get(result.run_id)
        status = finished.status if finished else "unknown"
        record_schedule_fire(result.market_id, slot, run_id=result.run_id, status=status)
        if finished and finished.status == "failed":
            from app.notifications import notify_run_failed

            notify_run_failed(
                market_id=result.market_id,
                run_id=result.run_id,
                error=finished.error or "Scheduled run failed",
            )

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._worker = None
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
