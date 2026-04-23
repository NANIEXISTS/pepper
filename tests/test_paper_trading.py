from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from trading_ai.alerts import AlertService
from trading_ai.execution import CcxtLiveOrderRouter, ExecutionEngine, PaperOrderRouter
from trading_ai.features import FeatureEngineer
from trading_ai.llm import LLMClient
from trading_ai.orchestration import build_default_paper_trading_service
from trading_ai.persistence import TradeAuditStore
from trading_ai.portfolio import PortfolioService
from trading_ai.reinforcement import ExecutionTimingCoordinator
from trading_ai.risk import RiskAuditAgent
from trading_ai.settings import TradingSettings


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
    async def fetch_dataframe(self, request):  # noqa: ANN001
        return _market_frame(request.lookback_bars)


@pytest.mark.asyncio
async def test_paper_trading_cycle_runs_and_emits_alert(tmp_path: Path) -> None:
    settings = TradingSettings()
    store = TradeAuditStore.from_database_url(f"sqlite+aiosqlite:///{(tmp_path / 'paper-cycle.db').as_posix()}")
    await store.create_schema()

    execution_engine = ExecutionEngine(
        settings=settings,
        risk_agent=RiskAuditAgent(settings.risk),
        audit_store=store,
        paper_router=PaperOrderRouter(),
        live_router=CcxtLiveOrderRouter(settings=settings.exchange, enabled=False),
    )
    service = build_default_paper_trading_service(
        market_data=FakeMarketDataService(),
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
    await store.close()
