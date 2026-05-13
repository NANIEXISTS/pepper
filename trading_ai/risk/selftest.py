from __future__ import annotations

from pydantic import BaseModel, Field

from ..core.enums import OrderSide
from ..core.models import OrderIntent, PortfolioSnapshot, RiskCheckContext
from ..settings import RiskSettings
from .agent import RiskAuditAgent


class DrawdownBreakerSelftestResult(BaseModel):
    passed: bool
    reason: str
    circuit_breaker_triggered: bool
    configured_max_daily_drawdown_fraction: float
    simulated_daily_pnl_fraction: float
    detail: str = Field(default="")


async def run_drawdown_breaker_selftest(risk_settings: RiskSettings) -> DrawdownBreakerSelftestResult:
    """Exercise the daily drawdown circuit breaker with a synthetic hostile portfolio.

    The breaker must veto a properly formed order when daily PnL has crossed the
    configured drawdown threshold. This is what the 28-day readiness checklist
    promises the operator, and we run it here for real rather than taking the
    operator's word for it.
    """

    agent = RiskAuditAgent(settings=risk_settings)
    threshold = risk_settings.max_daily_drawdown_fraction
    # Slip a hair past the threshold so the breaker should trigger.
    simulated_pnl_fraction = -(threshold + 0.001)
    portfolio = PortfolioSnapshot(
        equity=100_000.0,
        cash=100_000.0,
        daily_pnl_fraction=simulated_pnl_fraction,
        open_positions=0,
        stale_symbols=[],
    )
    order = OrderIntent(
        symbol="SELFTEST-USD",
        side=OrderSide.BUY,
        quantity=0.1,
        entry_price=100.0,
        stop_loss_price=99.0,
    )
    decision = await agent.run(RiskCheckContext(portfolio=portfolio, order=order))
    passed = (not decision.approved) and decision.circuit_breaker_triggered
    detail = (
        "Risk agent correctly vetoed a post-drawdown order and flagged the circuit breaker."
        if passed
        else "Risk agent did not halt trading after a simulated drawdown past the configured threshold."
    )
    return DrawdownBreakerSelftestResult(
        passed=passed,
        reason=decision.reason,
        circuit_breaker_triggered=decision.circuit_breaker_triggered,
        configured_max_daily_drawdown_fraction=threshold,
        simulated_daily_pnl_fraction=simulated_pnl_fraction,
        detail=detail,
    )
