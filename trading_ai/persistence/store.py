from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import desc, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ..core.models import ExecutionReport, OrderIntent, RiskDecision, TradeDecisionLog
from .models import (
    Base,
    LiveReadinessRecord,
    OperatorAuditEvent,
    PaperCycleJobRecord,
    PaperCycleRunRecord,
    PortfolioStateRecord,
    TradeAuditEvent,
)
from .schemas import LiveReadinessRecordView, OperatorAuditEventView, PortfolioStateView, TradeAuditEventView

if TYPE_CHECKING:
    from ..orchestration.models import PaperCycleJobCreate, PaperCycleJobView, PaperCycleRunView


@dataclass(slots=True)
class TradeAuditStore:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    @classmethod
    def from_database_url(cls, database_url: str) -> "TradeAuditStore":
        connect_args = {"timeout": 30.0} if database_url.startswith("sqlite") else {}
        engine = create_async_engine(database_url, future=True, connect_args=connect_args)
        return cls(
            engine=engine,
            session_factory=async_sessionmaker(engine, expire_on_commit=False),
        )

    async def create_schema(self) -> None:
        async with self.engine.begin() as connection:
            if self.engine.url.drivername.startswith("sqlite"):
                await connection.exec_driver_sql("PRAGMA busy_timeout=30000")
                await connection.exec_driver_sql("PRAGMA journal_mode=WAL")
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
            await self._commit(session)

    async def list_trade_events(self, *, limit: int = 50) -> list[TradeAuditEventView]:
        async with self.session_factory() as session:
            query = select(TradeAuditEvent).order_by(desc(TradeAuditEvent.id)).limit(limit)
            result = await session.execute(query)
            events = result.scalars().all()
            return [self._to_trade_event_view(event) for event in events]

    async def record_operator_action(
        self,
        *,
        username: str,
        role: str,
        action: str,
        resource: str,
        outcome: str,
        details: dict | None = None,
    ) -> None:
        async with self.session_factory() as session:
            event = OperatorAuditEvent(
                username=username,
                role=role,
                action=action,
                resource=resource,
                outcome=outcome,
                details_payload=details or {},
            )
            session.add(event)
            await self._commit(session)

    async def list_operator_actions(self, *, limit: int = 50) -> list[OperatorAuditEventView]:
        async with self.session_factory() as session:
            query = select(OperatorAuditEvent).order_by(desc(OperatorAuditEvent.id)).limit(limit)
            result = await session.execute(query)
            events = result.scalars().all()
            return [self._to_operator_event_view(event) for event in events]

    async def save_portfolio_state(self, state: PortfolioStateView) -> PortfolioStateView:
        async with self.session_factory() as session:
            record = await session.get(PortfolioStateRecord, state.key)
            if record is None:
                record = PortfolioStateRecord(
                    key=state.key,
                    cash=state.cash,
                    realized_pnl=state.realized_pnl,
                    daily_anchor_equity=state.daily_anchor_equity,
                    daily_anchor_date=state.daily_anchor_date,
                    positions_payload=state.positions_payload,
                )
                session.add(record)
            else:
                record.cash = state.cash
                record.realized_pnl = state.realized_pnl
                record.daily_anchor_equity = state.daily_anchor_equity
                record.daily_anchor_date = state.daily_anchor_date
                record.positions_payload = state.positions_payload
                record.updated_at = datetime.now(UTC)
            await self._commit(session)
            await session.refresh(record)
            return self._to_portfolio_state_view(record)

    async def load_portfolio_state(self, *, key: str = "paper-default") -> PortfolioStateView | None:
        async with self.session_factory() as session:
            record = await session.get(PortfolioStateRecord, key)
            if record is None:
                return None
            return self._to_portfolio_state_view(record)

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
            await self._commit(session)
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
            await self._commit(session)
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
            await self._commit(session)
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

            await self._commit(session)
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

    async def record_live_readiness_event(
        self,
        *,
        kind: str,
        recorded_by: str,
        payload: dict,
    ) -> LiveReadinessRecordView:
        async with self.session_factory() as session:
            record = LiveReadinessRecord(
                kind=kind,
                recorded_by=recorded_by,
                payload=payload,
            )
            session.add(record)
            await self._commit(session)
            await session.refresh(record)
            return self._to_live_readiness_view(record)

    async def list_live_readiness_events(
        self,
        *,
        kind: str | None = None,
        limit: int = 50,
    ) -> list[LiveReadinessRecordView]:
        async with self.session_factory() as session:
            query = select(LiveReadinessRecord)
            if kind is not None:
                query = query.where(LiveReadinessRecord.kind == kind)
            query = query.order_by(desc(LiveReadinessRecord.id)).limit(limit)
            result = await session.execute(query)
            records = result.scalars().all()
            return [self._to_live_readiness_view(record) for record in records]

    async def latest_live_readiness_events(self) -> dict[str, LiveReadinessRecordView]:
        async with self.session_factory() as session:
            query = select(LiveReadinessRecord).order_by(desc(LiveReadinessRecord.id))
            result = await session.execute(query)
            latest: dict[str, LiveReadinessRecordView] = {}
            for record in result.scalars().all():
                if record.kind in latest:
                    continue
                latest[record.kind] = self._to_live_readiness_view(record)
            return latest

    async def close(self) -> None:
        await self.engine.dispose()

    async def _commit(self, session: AsyncSession) -> None:
        for attempt in range(5):
            try:
                await session.commit()
                return
            except OperationalError as exc:
                if "database is locked" not in str(exc).lower() or attempt == 4:
                    raise
                await session.rollback()
                await asyncio.sleep(0.05 * (attempt + 1))

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

    def _to_trade_event_view(self, event: TradeAuditEvent) -> TradeAuditEventView:
        return TradeAuditEventView(
            id=event.id,
            created_at=event.created_at,
            agent_name=event.agent_name,
            symbol=event.symbol,
            signal=event.signal,
            confidence=event.confidence,
            risk_check_passed=event.risk_check_passed,
            action_taken=event.action_taken,
            rationale=event.rationale,
            order_payload=event.order_payload,
            risk_reason=event.risk_reason,
            risk_fraction=event.risk_fraction,
            router=event.router,
            order_status=event.order_status,
            report_payload=event.report_payload,
            metadata_payload=event.metadata_payload,
        )

    def _to_portfolio_state_view(self, record: PortfolioStateRecord) -> PortfolioStateView:
        return PortfolioStateView(
            key=record.key,
            updated_at=record.updated_at,
            cash=record.cash,
            realized_pnl=record.realized_pnl,
            daily_anchor_equity=record.daily_anchor_equity,
            daily_anchor_date=record.daily_anchor_date,
            positions_payload=record.positions_payload,
        )

    def _to_operator_event_view(self, event: OperatorAuditEvent) -> OperatorAuditEventView:
        return OperatorAuditEventView(
            id=event.id,
            created_at=event.created_at,
            username=event.username,
            role=event.role,
            action=event.action,
            resource=event.resource,
            outcome=event.outcome,
            details_payload=event.details_payload,
        )

    def _to_live_readiness_view(self, record: LiveReadinessRecord) -> LiveReadinessRecordView:
        return LiveReadinessRecordView(
            id=record.id,
            recorded_at=record.recorded_at,
            kind=record.kind,
            recorded_by=record.recorded_by,
            payload=record.payload,
        )
