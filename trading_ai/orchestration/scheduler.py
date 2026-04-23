from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field

from ..alerts import AlertService
from ..logging_config import get_logger
from ..persistence import TradeAuditStore
from .models import PaperCycleJobCreate, PaperCycleJobView, PaperCycleRunView, PaperTradingCycleResult
from .paper_trading import PaperTradingService

logger = get_logger(__name__)


@dataclass(slots=True)
class PaperTradingScheduler:
    paper_trading_service: PaperTradingService
    audit_store: TradeAuditStore
    alert_service: AlertService
    _tasks: dict[int, asyncio.Task[None]] = field(default_factory=dict)

    async def initialize(self) -> None:
        jobs = await self.audit_store.list_paper_cycle_jobs(active_only=True)
        for job in jobs:
            self._ensure_task(job.id)

    async def close(self) -> None:
        task_ids = list(self._tasks.keys())
        for job_id in task_ids:
            await self._stop_task(job_id)

    async def create_job(self, payload: PaperCycleJobCreate) -> PaperCycleJobView:
        job = await self.audit_store.create_paper_cycle_job(payload)
        if job.is_active:
            self._ensure_task(job.id)
        return job

    async def list_jobs(self) -> list[PaperCycleJobView]:
        return await self.audit_store.list_paper_cycle_jobs()

    async def get_job(self, job_id: int) -> PaperCycleJobView | None:
        return await self.audit_store.get_paper_cycle_job(job_id)

    async def start_job(self, job_id: int) -> PaperCycleJobView | None:
        job = await self.audit_store.set_paper_cycle_job_active(job_id, True)
        if job is None:
            return None
        self._ensure_task(job.id)
        return job

    async def pause_job(self, job_id: int) -> PaperCycleJobView | None:
        job = await self.audit_store.set_paper_cycle_job_active(job_id, False)
        if job is None:
            return None
        await self._stop_task(job_id)
        return job

    async def run_job_once(self, job_id: int, *, source: str = "manual-job") -> PaperTradingCycleResult:
        job = await self.audit_store.get_paper_cycle_job(job_id)
        if job is None:
            raise LookupError(f"Paper cycle job {job_id} was not found.")
        return await self._execute_cycle(
            symbol=job.symbol,
            timeframe=job.timeframe,
            lookback_bars=job.lookback_bars,
            source=source,
            job_id=job.id,
        )

    async def run_ad_hoc_cycle(self, *, symbol: str, timeframe: str, lookback_bars: int) -> PaperTradingCycleResult:
        return await self._execute_cycle(
            symbol=symbol,
            timeframe=timeframe,
            lookback_bars=lookback_bars,
            source="manual",
            job_id=None,
        )

    async def list_runs(self, *, limit: int = 50, job_id: int | None = None) -> list[PaperCycleRunView]:
        return await self.audit_store.list_cycle_runs(limit=limit, job_id=job_id)

    async def _execute_cycle(
        self,
        *,
        symbol: str,
        timeframe: str,
        lookback_bars: int,
        source: str,
        job_id: int | None,
    ) -> PaperTradingCycleResult:
        run_id = await self.audit_store.record_cycle_run_started(
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            job_id=job_id,
        )
        try:
            cycle = await self.paper_trading_service.run_cycle(symbol, timeframe, lookback_bars)
        except Exception as exc:
            await self.audit_store.record_cycle_run_finished(
                run_id,
                status="failed",
                error_message=str(exc),
            )
            self.alert_service.emit(
                "error",
                f"Paper cycle failed for {symbol}.",
                symbol=symbol,
                timeframe=timeframe,
                source=source,
                job_id=job_id,
                error=str(exc),
            )
            raise

        execution_status = cycle.execution_report.status.value if cycle.execution_report is not None else "none"
        await self.audit_store.record_cycle_run_finished(
            run_id,
            status="completed",
            cycle_payload=cycle.model_dump(mode="json"),
            execution_status=execution_status,
            trade_executed=bool(cycle.metadata.get("trade_executed", False)),
        )
        return cycle

    def _ensure_task(self, job_id: int) -> None:
        existing = self._tasks.get(job_id)
        if existing is not None and not existing.done():
            return
        task = asyncio.create_task(self._job_loop(job_id), name=f"paper-cycle-job-{job_id}")
        task.add_done_callback(lambda done_task, job_id=job_id: self._clear_task(job_id, done_task))
        self._tasks[job_id] = task

    async def _stop_task(self, job_id: int) -> None:
        task = self._tasks.pop(job_id, None)
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _job_loop(self, job_id: int) -> None:
        while True:
            job = await self.audit_store.get_paper_cycle_job(job_id)
            if job is None or not job.is_active:
                return

            started = asyncio.get_running_loop().time()
            try:
                await self._execute_cycle(
                    symbol=job.symbol,
                    timeframe=job.timeframe,
                    lookback_bars=job.lookback_bars,
                    source="scheduler",
                    job_id=job.id,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(
                    "scheduled_cycle_failed",
                    job_id=job.id,
                    symbol=job.symbol,
                    timeframe=job.timeframe,
                    error=str(exc),
                )

            elapsed = asyncio.get_running_loop().time() - started
            sleep_seconds = max(job.interval_seconds - elapsed, 1.0)
            await asyncio.sleep(sleep_seconds)

    def _clear_task(self, job_id: int, task: asyncio.Task[None]) -> None:
        current = self._tasks.get(job_id)
        if current is task:
            self._tasks.pop(job_id, None)
