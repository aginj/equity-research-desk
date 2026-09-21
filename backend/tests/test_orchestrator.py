import asyncio
from datetime import UTC, datetime

import pytest
from sqlmodel import Session, select

from app.agents.orchestrator import RunBus
from app.db import AnalysisRunRow
from app.domain import RunEvent
from app.store import get_engine, init_db, recover_stale_runs


def _event(run_id: str, stage: str = "ingest") -> RunEvent:
    return RunEvent(
        run_id=run_id,
        stage=stage,  # type: ignore[arg-type]
        message="m",
        at=datetime.now(UTC),
        progress=0.1,
    )


@pytest.mark.asyncio
async def test_run_bus_replays_history_and_closes():
    bus = RunBus()
    bus.open("r1")
    await bus.publish(_event("r1"))
    queue = bus.subscribe("r1")
    await bus.publish(_event("r1", "policy"))
    await bus.close("r1")

    first = await queue.get()
    second = await queue.get()
    done = await queue.get()
    assert first is not None and first.stage == "ingest"
    assert second is not None and second.stage == "policy"
    assert done is None

    # Late subscriber to a closed run gets history then an immediate close.
    late = bus.subscribe("r1")
    assert (await late.get()) is not None
    assert (await late.get()) is not None
    assert (await late.get()) is None


@pytest.mark.asyncio
async def test_run_bus_unknown_run_closes_immediately():
    bus = RunBus()
    queue = bus.subscribe("never-opened")
    assert (await asyncio.wait_for(queue.get(), timeout=1)) is None


@pytest.mark.asyncio
async def test_run_bus_history_is_bounded():
    bus = RunBus(max_runs=3)
    for i in range(10):
        run_id = f"r{i}"
        bus.open(run_id)
        await bus.publish(_event(run_id))
        await bus.close(run_id)
    assert len(bus._history) == 3
    assert set(bus._history) == {"r7", "r8", "r9"}
    assert bus._closed <= set(bus._history)


def test_recover_stale_runs_marks_running_as_failed():
    init_db()
    engine = get_engine()
    with Session(engine) as session:
        session.add(
            AnalysisRunRow(
                id="stale-run",
                status="running",
                stage="ingest",
                risk_appetite="balanced",
                market_id="us",
                started_at=datetime.now(UTC),
            )
        )
        session.commit()
    try:
        assert recover_stale_runs() >= 1
        with Session(engine) as session:
            row = session.exec(select(AnalysisRunRow).where(AnalysisRunRow.id == "stale-run")).one()
            assert row.status == "failed"
            assert row.stage == "failed"
            assert row.finished_at is not None
            assert "restart" in (row.error or "")
    finally:
        with Session(engine) as session:
            row = session.get(AnalysisRunRow, "stale-run")
            if row:
                session.delete(row)
                session.commit()
