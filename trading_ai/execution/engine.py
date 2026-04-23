from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from ..core.enums import OrderStatus, TradeSignal, TradingMode
from ..core.models import (
    ExecutionReport,
    OrderIntent,
    PortfolioSnapshot,
    RiskCheckContext,
    TradeDecisionLog,
)
from ..logging_config import get_logger
from ..persistence.store import TradeAuditStore
from ..risk.agent import RiskAuditAgent
from ..settings import TradingSettings
from .router import OrderRouter, PaperOrderRouter

logger = get_logger(__name__)


class SupportsOrderRouting(Protocol):
    async def submit_order(self, order: OrderIntent) -> ExecutionReport:
        ...


@dataclass(slots=True)
class ExecutionEngine:
    settings: TradingSettings
    risk_agent: RiskAuditAgent
    audit_store: TradeAuditStore
    paper_router: PaperOrderRouter
    live_router: OrderRouter

    async def place_order(
        self,
        *,
        agent_name: str,
        signal: TradeSignal,
        confidence: float,
        rationale: str,
        order: OrderIntent,
        portfolio: PortfolioSnapshot,
        metadata: dict | None = None,
    ) -> ExecutionReport:
        context = RiskCheckContext(
            portfolio=portfolio,
            order=order,
            mode=self.settings.app_mode,
        )
        risk_decision = await self.risk_agent.run(context)

        if not risk_decision.approved:
            report = ExecutionReport(
                order_id=f"rejected-{uuid4().hex[:12]}",
                status=OrderStatus.REJECTED,
                router="risk-gate",
                submitted_at=datetime.now(UTC),
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                message=risk_decision.reason,
            )
            trade_decision = TradeDecisionLog(
                agent_name=agent_name,
                symbol=order.symbol,
                signal=signal,
                confidence=confidence,
                risk_check_passed=False,
                action_taken="rejected",
                rationale=rationale,
                metadata=metadata or {},
            )
            await self.audit_store.record_trade_event(trade_decision, order, risk_decision, report)
            logger.warning(
                "trade_decision",
                agent_name=agent_name,
                symbol=order.symbol,
                signal=signal.value,
                confidence=confidence,
                risk_check_passed=False,
                action_taken="rejected",
                reason=risk_decision.reason,
            )
            return report

        router = self._select_router()
        report = await router.submit_order(order)
        trade_decision = TradeDecisionLog(
            agent_name=agent_name,
            symbol=order.symbol,
            signal=signal,
            confidence=confidence,
            risk_check_passed=True,
            action_taken=report.status.value,
            rationale=rationale,
            metadata=metadata or {},
        )
        await self.audit_store.record_trade_event(trade_decision, order, risk_decision, report)
        logger.info(
            "trade_decision",
            agent_name=agent_name,
            symbol=order.symbol,
            signal=signal.value,
            confidence=confidence,
            risk_check_passed=True,
            action_taken=report.status.value,
            router=report.router,
        )
        return report

    def _select_router(self) -> SupportsOrderRouting:
        if self.settings.app_mode == TradingMode.LIVE:
            return self.live_router
        return self.paper_router
