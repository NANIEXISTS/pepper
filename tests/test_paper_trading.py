from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from trading_ai.alerts import AlertService
from trading_ai.agents import TraderAgent
from trading_ai.agents.models import AgentContext, StrategyOutput
from trading_ai.core.enums import TradeSignal
from trading_ai.execution import CcxtLiveOrderRouter, ExecutionEngine, PaperOrderRouter
from trading_ai.features import FeatureEngineer
from trading_ai.llm import LLMClient
from trading_ai.orchestration import build_default_paper_trading_service
from trading_ai.persistence import TradeAuditStore
from trading_ai.portfolio import PortfolioService, Position
from trading_ai.reinforcement import ExecutionTimingCoordinator
from trading_ai.risk import RiskAuditAgent
from trading_ai.settings import PaperTradingSettings, RiskSettings, TradingSettings


def _market_frame(rows: int = 600) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=rows, freq="1h", tz="UTC")
    close = [100 + (i * 0.02) + (2.5 * math.sin(i / 10)) for i in range(rows)]
    close[-10:] = [close[-11] + (i * 0.15) for i in range(1, 11)]
    frame = pd.DataFrame(
        {
            "symbol": ["BTC-USD"] * rows,
            "timeframe": ["1h"] * rows,
            "open": [price - 0.2 for price in close],
            "high": [price + 0.4 for price in close],
            "low": [price - 0.6 for price in close],
            "close": close,
            "volume": [1000 + (i % 15) * 50 for i in range(rows)],
        },
        index=index,
    )
    frame.index.name = "timestamp"
    return frame


class FakeMarketDataService:
    def __init__(self) -> None:
        self.requested_symbols: list[str] = []

    async def fetch_dataframe(self, request):  # noqa: ANN001
        self.requested_symbols.append(request.symbol)
        return _market_frame(request.lookback_bars)


@pytest.mark.asyncio
async def test_paper_trading_cycle_runs_and_emits_alert(tmp_path: Path) -> None:
    settings = TradingSettings()
    store = TradeAuditStore.from_database_url(f"sqlite+aiosqlite:///{(tmp_path / 'paper-cycle.db').as_posix()}")
    await store.create_schema()
    market_data = FakeMarketDataService()

    execution_engine = ExecutionEngine(
        settings=settings,
        risk_agent=RiskAuditAgent(settings.risk),
        audit_store=store,
        paper_router=PaperOrderRouter(),
        live_router=CcxtLiveOrderRouter(settings=settings.exchange, enabled=False),
    )
    service = build_default_paper_trading_service(
        market_data=market_data,
        feature_engineer=FeatureEngineer(),
        execution_engine=execution_engine,
        portfolio_service=PortfolioService(starting_cash=settings.paper_trading.starting_cash),
        alert_service=AlertService(),
        llm_client=LLMClient(settings.llm),
        paper_settings=settings.paper_trading,
        risk_settings=settings.risk,
        execution_timing=ExecutionTimingCoordinator(settings.reinforcement),
    )

    cycle = await service.run_cycle("BTC-USD", "1h", 600)

    assert cycle.symbol == "BTC-USD"
    assert cycle.analysis.agent_name == "analyst-agent"
    assert cycle.strategy.signal.value in {"BUY", "SELL", "HOLD"}
    assert cycle.alert is not None
    assert market_data.requested_symbols[0] == "BTC-USD"
    await store.close()


@pytest.mark.asyncio
async def test_paper_trading_buy_reserves_cash_for_slippage() -> None:
    settings = TradingSettings(
        paper_trading=PaperTradingSettings(signal_confidence_threshold=0.0),
        risk=RiskSettings(max_per_trade_risk_fraction=0.05),
    )
    frame = pd.DataFrame(
        {"close": [100.0], "atr_14": [0.5], "macd_histogram": [0.01]},
        index=pd.date_range("2025-01-01", periods=1, freq="1h", tz="UTC"),
    )
    context = AgentContext(
        symbol="BTC-USD",
        timeframe="1h",
        market_frame=frame,
        features=frame,
        portfolio_equity=100_000.0,
        available_cash=100_000.0,
        positions={},
    )
    strategy = StrategyOutput(
        agent_name="test-strategy",
        signal=TradeSignal.BUY,
        confidence=0.25,
        rationale="Force BUY to test sizing capacity.",
    )

    trader = TraderAgent(
        risk_settings=settings.risk,
        paper_settings=settings.paper_trading,
        execution_timing=ExecutionTimingCoordinator(settings.reinforcement),
    )
    order = await trader.run(context, strategy)

    assert order is not None
    simulated_fill_price = order.entry_price * 1.0002
    assert order.quantity * simulated_fill_price <= context.available_cash


@pytest.mark.asyncio
async def test_paper_trading_cycle_refreshes_other_open_position_prices(tmp_path: Path) -> None:
    settings = TradingSettings()
    store = TradeAuditStore.from_database_url(f"sqlite+aiosqlite:///{(tmp_path / 'paper-cycle-multi.db').as_posix()}")
    await store.create_schema()
    market_data = FakeMarketDataService()
    portfolio_service = PortfolioService(starting_cash=settings.paper_trading.starting_cash)
    portfolio_service.positions["ETH-USD"] = Position(
        symbol="ETH-USD",
        quantity=1.0,
        average_entry_price=100.0,
        last_price=100.0,
    )

    execution_engine = ExecutionEngine(
        settings=settings,
        risk_agent=RiskAuditAgent(settings.risk),
        audit_store=store,
        paper_router=PaperOrderRouter(),
        live_router=CcxtLiveOrderRouter(settings=settings.exchange, enabled=False),
    )
    service = build_default_paper_trading_service(
        market_data=market_data,
        feature_engineer=FeatureEngineer(),
        execution_engine=execution_engine,
        portfolio_service=portfolio_service,
        alert_service=AlertService(),
        llm_client=LLMClient(settings.llm),
        paper_settings=settings.paper_trading,
        risk_settings=settings.risk,
        execution_timing=ExecutionTimingCoordinator(settings.reinforcement),
    )

    cycle = await service.run_cycle("BTC-USD", "1h", 600)

    assert cycle.portfolio.stale_symbols == []
    assert "BTC-USD" in market_data.requested_symbols
    assert "ETH-USD" in market_data.requested_symbols
    await store.close()
