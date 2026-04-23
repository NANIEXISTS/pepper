from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ..core.models import ExecutionReport, OrderIntent, RiskDecision, TradeDecisionLog
from .models import Base, TradeAuditEvent


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

    async def close(self) -> None:
        await self.engine.dispose()
