from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ..core.models import ExecutionReport, OrderIntent, RiskDecision, TradeDecisionLog
from .models import Base, PaperCycleJobRecord, PaperCycleRunRecord, TradeAuditEvent

if TYPE_CHECKING:
    from ..orchestration.models import PaperCycleJobCreate, PaperCycleJobView, PaperCycleRunView


@dataclass(slots=True)
class TradeAuditStore:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    @classmethod
    def from_database_url(cls, database_url: str) -> "TradeAuditStore":
        engine = create_async_engine(database_url, future=True)
        return cls(
            engine=engine,
            session_factory=async_sessionmaker(engine, expire_on_commit=False),
        )

    async def create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def record_trade_event(
        self,
        decision: TradeDecisionLog,
        order: OrderIntent,
        risk_decision: RiskDecision,
        report: ExecutionReport,
    ) -> None:
        async with self.session_factory() as session:
            event = TradeAuditEvent(
                agent_name=decision.agent_name,
                symbol=decision.symbol,
                signal=decision.signal.value,
                confidence=decision.confidence,
                risk_check_passed=decision.risk_check_passed,
                action_taken=decision.action_taken,
                rationale=decision.rationale,
                order_payload=order.model_dump(mode="json"),
                risk_reason=risk_decision.reason,
                risk_fraction=risk_decision.risk_fraction,
                router=report.router,
                order_status=report.status.value,
                report_payload=report.model_dump(mode="json"),
                metadata_payload=decision.metadata,
            )
            session.add(event)
            await session.commit()

    async def create_paper_cycle_job(self, payload: PaperCycleJobCreate) -> PaperCycleJobView:
        async with self.session_factory() as session:
            job = PaperCycleJobRecord(
                symbol=payload.symbol,
                timeframe=payload.timeframe,
                lookback_bars=payload.lookback_bars,
                interval_seconds=payload.interval_seconds,
                is_active=payload.auto_start,
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return self._to_job_view(job)

    async def get_paper_cycle_job(self, job_id: int) -> PaperCycleJobView | None:
        async with self.session_factory() as session:
            job = await session.get(PaperCycleJobRecord, job_id)
            if job is None:
                return None
            return self._to_job_view(job)

    async def list_paper_cycle_jobs(self, *, active_only: bool = False) -> list[PaperCycleJobView]:
        async with self.session_factory() as session:
            query = select(PaperCycleJobRecord).order_by(PaperCycleJobRecord.id.asc())
            if active_only:
                query = query.where(PaperCycleJobRecord.is_active.is_(True))
            result = await session.execute(query)
            jobs = result.scalars().all()
            return [self._to_job_view(job) for job in jobs]

    async def set_paper_cycle_job_active(self, job_id: int, is_active: bool) -> PaperCycleJobView | None:
        async with self.session_factory() as session:
            job = await session.get(PaperCycleJobRecord, job_id)
            if job is None:
                return None
            job.is_active = is_active
            job.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(job)
            return self._to_job_view(job)

    async def record_cycle_run_started(
        self,
        *,
        source: str,
        symbol: str,
        timeframe: str,
        job_id: int | None = None,
    ) -> int:
        async with self.session_factory() as session:
            now = datetime.now(UTC)
            run = PaperCycleRunRecord(
                job_id=job_id,
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                started_at=now,
                status="running",
            )
            session.add(run)
            if job_id is not None:
                job = await session.get(PaperCycleJobRecord, job_id)
                if job is not None:
                    job.last_started_at = now
                    job.last_status = "running"
                    job.last_error = None
                    job.updated_at = now
            await session.commit()
            await session.refresh(run)
            return run.id

    async def record_cycle_run_finished(
        self,
        run_id: int,
        *,
        status: str,
        cycle_payload: dict | None = None,
        execution_status: str | None = None,
        trade_executed: bool = False,
        error_message: str | None = None,
    ) -> PaperCycleRunView | None:
        async with self.session_factory() as session:
            run = await session.get(PaperCycleRunRecord, run_id)
            if run is None:
                return None

            now = datetime.now(UTC)
            run.finished_at = now
            run.status = status
            run.execution_status = execution_status
            run.trade_executed = trade_executed
            run.error_message = error_message
            run.cycle_payload = cycle_payload

            if run.job_id is not None:
                job = await session.get(PaperCycleJobRecord, run.job_id)
                if job is not None:
                    job.last_finished_at = now
                    job.last_status = status
                    job.last_error = error_message
                    job.updated_at = now

            await session.commit()
            await session.refresh(run)
            return self._to_run_view(run)

    async def list_cycle_runs(self, *, limit: int = 50, job_id: int | None = None) -> list[PaperCycleRunView]:
        async with self.session_factory() as session:
            query = select(PaperCycleRunRecord)
            if job_id is not None:
                query = query.where(PaperCycleRunRecord.job_id == job_id)
            query = query.order_by(desc(PaperCycleRunRecord.id)).limit(limit)
            result = await session.execute(query)
            runs = result.scalars().all()
            return [self._to_run_view(run) for run in runs]

    async def close(self) -> None:
        await self.engine.dispose()

    def _to_job_view(self, job: PaperCycleJobRecord) -> PaperCycleJobView:
        from ..orchestration.models import PaperCycleJobView

        return PaperCycleJobView(
            id=job.id,
            created_at=job.created_at,
            updated_at=job.updated_at,
            symbol=job.symbol,
            timeframe=job.timeframe,
            lookback_bars=job.lookback_bars,
            interval_seconds=job.interval_seconds,
            is_active=job.is_active,
            last_started_at=job.last_started_at,
            last_finished_at=job.last_finished_at,
            last_status=job.last_status,
            last_error=job.last_error,
        )

    def _to_run_view(self, run: PaperCycleRunRecord) -> PaperCycleRunView:
        from ..orchestration.models import PaperCycleRunView

        return PaperCycleRunView(
            id=run.id,
            job_id=run.job_id,
            source=run.source,
            symbol=run.symbol,
            timeframe=run.timeframe,
            started_at=run.started_at,
            finished_at=run.finished_at,
            status=run.status,
            execution_status=run.execution_status,
            trade_executed=run.trade_executed,
            error_message=run.error_message,
            cycle_payload=run.cycle_payload,
        )
