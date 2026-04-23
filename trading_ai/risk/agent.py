from __future__ import annotations

from dataclasses import dataclass

from ..core.models import RiskCheckContext, RiskDecision
from ..settings import RiskSettings


@dataclass(slots=True)
class RiskAuditAgent:
    settings: RiskSettings

    async def run(self, context: RiskCheckContext) -> RiskDecision:
        if self.settings.stop_loss_required and context.order.stop_loss_price is None:
            return RiskDecision(
                approved=False,
                reason="stop_loss_required",
            )

        if context.portfolio.daily_pnl_fraction <= -self.settings.max_daily_drawdown_fraction:
            return RiskDecision(
                approved=False,
                reason="daily_drawdown_circuit_breaker",
                circuit_breaker_triggered=True,
            )

        if context.portfolio.open_positions >= self.settings.max_positions:
            return RiskDecision(
                approved=False,
                reason="max_positions_reached",
            )

        risk_fraction = context.order.risk_fraction(context.portfolio.equity)
        if risk_fraction > self.settings.max_per_trade_risk_fraction:
            return RiskDecision(
                approved=False,
                reason="per_trade_risk_limit_exceeded",
                risk_fraction=risk_fraction,
            )

        return RiskDecision(
            approved=True,
            reason="approved",
            risk_fraction=risk_fraction,
        )
