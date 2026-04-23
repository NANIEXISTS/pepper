from __future__ import annotations

import pytest

from trading_ai.core.enums import OrderSide
from trading_ai.core.models import OrderIntent, PortfolioSnapshot, RiskCheckContext
from trading_ai.risk import RiskAuditAgent
from trading_ai.settings import RiskSettings


@pytest.mark.asyncio
async def test_risk_agent_approves_trade_within_limits() -> None:
    agent = RiskAuditAgent(RiskSettings())
    context = RiskCheckContext(
        portfolio=PortfolioSnapshot(equity=10_000, daily_pnl_fraction=-0.01, open_positions=2),
        order=OrderIntent(
            symbol="BTC-USD",
            side=OrderSide.BUY,
            quantity=0.1,
            entry_price=100,
            stop_loss_price=99,
        ),
    )

    decision = await agent.run(context)

    assert decision.approved is True
    assert decision.reason == "approved"
    assert decision.risk_fraction is not None
    assert decision.risk_fraction < 0.01


@pytest.mark.asyncio
async def test_risk_agent_rejects_trade_above_risk_limit() -> None:
    agent = RiskAuditAgent(RiskSettings())
    context = RiskCheckContext(
        portfolio=PortfolioSnapshot(equity=10_000, daily_pnl_fraction=0.0, open_positions=0),
        order=OrderIntent(
            symbol="BTC-USD",
            side=OrderSide.BUY,
            quantity=200,
            entry_price=100,
            stop_loss_price=99,
        ),
    )

    decision = await agent.run(context)

    assert decision.approved is False
    assert decision.reason == "per_trade_risk_limit_exceeded"
    assert decision.risk_fraction is not None
    assert decision.risk_fraction > 0.01


@pytest.mark.asyncio
async def test_risk_agent_triggers_daily_drawdown_circuit_breaker() -> None:
    agent = RiskAuditAgent(RiskSettings())
    context = RiskCheckContext(
        portfolio=PortfolioSnapshot(equity=10_000, daily_pnl_fraction=-0.06, open_positions=0),
        order=OrderIntent(
            symbol="BTC-USD",
            side=OrderSide.BUY,
            quantity=0.1,
            entry_price=100,
            stop_loss_price=99,
        ),
    )

    decision = await agent.run(context)

    assert decision.approved is False
    assert decision.circuit_breaker_triggered is True
    assert decision.reason == "daily_drawdown_circuit_breaker"


@pytest.mark.asyncio
async def test_risk_agent_rejects_stale_portfolio_prices() -> None:
    agent = RiskAuditAgent(RiskSettings())
    context = RiskCheckContext(
        portfolio=PortfolioSnapshot(
            equity=10_000,
            daily_pnl_fraction=0.0,
            open_positions=1,
            stale_symbols=["ETH-USD"],
        ),
        order=OrderIntent(
            symbol="BTC-USD",
            side=OrderSide.BUY,
            quantity=0.1,
            entry_price=100,
            stop_loss_price=99,
        ),
    )

    decision = await agent.run(context)

    assert decision.approved is False
    assert decision.reason == "stale_portfolio_prices"
