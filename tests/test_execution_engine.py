from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from trading_ai.core.enums import OrderSide, OrderStatus, TradeSignal, TradingMode
from trading_ai.core.models import OrderIntent, PortfolioSnapshot
from trading_ai.execution import ExecutionEngine, LiveOrderRouter, PaperOrderRouter
from trading_ai.persistence.models import TradeAuditEvent
from trading_ai.persistence.store import TradeAuditStore
from trading_ai.risk import RiskAuditAgent
from trading_ai.settings import (
    ExecutionSettings,
    LoggingSettings,
    PersistenceSettings,
    RiskSettings,
    TradingSettings,
)


def _settings(db_path: Path) -> TradingSettings:
    return TradingSettings(
        app_mode=TradingMode.PAPER,
        risk=RiskSettings(),
        execution=ExecutionSettings(),
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}"),
        logging=LoggingSettings(level="INFO"),
    )


@pytest.mark.asyncio
async def test_execution_engine_routes_paper_trade_and_persists(tmp_path: Path) -> None:
    settings = _settings(tmp_path / "paper.db")
    store = TradeAuditStore.from_database_url(settings.persistence.database_url)
    await store.create_schema()
    engine = ExecutionEngine(
        settings=settings,
        risk_agent=RiskAuditAgent(settings.risk),
        audit_store=store,
        paper_router=PaperOrderRouter(),
        live_router=LiveOrderRouter(),
    )

    report = await engine.place_order(
        agent_name="strategy-agent",
        signal=TradeSignal.BUY,
        confidence=0.71,
        rationale="EMA and RSI aligned.",
        order=OrderIntent(
            symbol="BTC-USD",
            side=OrderSide.BUY,
            quantity=0.1,
            entry_price=100,
            stop_loss_price=99,
        ),
        portfolio=PortfolioSnapshot(equity=10_000, daily_pnl_fraction=-0.01, open_positions=1),
        metadata={"source": "test"},
    )

    assert report.status == OrderStatus.FILLED
    assert report.router == "paper"

    async with store.session_factory() as session:
        events = (await session.execute(select(TradeAuditEvent))).scalars().all()

    assert len(events) == 1
    assert events[0].risk_check_passed is True
    await store.close()


@pytest.mark.asyncio
async def test_execution_engine_persists_risk_veto(tmp_path: Path) -> None:
    settings = _settings(tmp_path / "veto.db")
    store = TradeAuditStore.from_database_url(settings.persistence.database_url)
    await store.create_schema()
    engine = ExecutionEngine(
        settings=settings,
        risk_agent=RiskAuditAgent(settings.risk),
        audit_store=store,
        paper_router=PaperOrderRouter(),
        live_router=LiveOrderRouter(),
    )

    report = await engine.place_order(
        agent_name="strategy-agent",
        signal=TradeSignal.BUY,
        confidence=0.55,
        rationale="Oversized trade should be vetoed.",
        order=OrderIntent(
            symbol="BTC-USD",
            side=OrderSide.BUY,
            quantity=200,
            entry_price=100,
            stop_loss_price=99,
        ),
        portfolio=PortfolioSnapshot(equity=10_000, daily_pnl_fraction=0.0, open_positions=0),
    )

    assert report.status == OrderStatus.REJECTED
    assert report.router == "risk-gate"

    async with store.session_factory() as session:
        events = (await session.execute(select(TradeAuditEvent))).scalars().all()

    assert len(events) == 1
    assert events[0].risk_check_passed is False
    assert events[0].risk_reason == "per_trade_risk_limit_exceeded"
    await store.close()
