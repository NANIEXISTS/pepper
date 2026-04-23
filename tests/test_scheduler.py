from __future__ import annotations

import asyncio
import math
from pathlib import Path

import pandas as pd
import pytest

from trading_ai.alerts import AlertService
from trading_ai.execution import CcxtLiveOrderRouter, ExecutionEngine, PaperOrderRouter
from trading_ai.features import FeatureEngineer
from trading_ai.llm import LLMClient
from trading_ai.orchestration import PaperCycleJobCreate, PaperTradingScheduler, build_default_paper_trading_service
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
    def __init__(self, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = delay_seconds

    async def fetch_dataframe(self, request):  # noqa: ANN001
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        return _market_frame(request.lookback_bars)


def _build_scheduler(tmp_path: Path, *, delay_seconds: float = 0.0) -> tuple[TradeAuditStore, PaperTradingScheduler]:
    settings = TradingSettings()
    store = TradeAuditStore.from_database_url(f"sqlite+aiosqlite:///{(tmp_path / 'scheduler.db').as_posix()}")
    execution_engine = ExecutionEngine(
        settings=settings,
        risk_agent=RiskAuditAgent(settings.risk),
        audit_store=store,
        paper_router=PaperOrderRouter(),
        live_router=CcxtLiveOrderRouter(settings=settings.exchange, enabled=False),
    )
    alert_service = AlertService()
    service = build_default_paper_trading_service(
        market_data=FakeMarketDataService(delay_seconds=delay_seconds),
        feature_engineer=FeatureEngineer(),
        execution_engine=execution_engine,
        portfolio_service=PortfolioService(starting_cash=settings.paper_trading.starting_cash),
        alert_service=alert_service,
        llm_client=LLMClient(settings.llm),
        paper_settings=settings.paper_trading,
        risk_settings=settings.risk,
        execution_timing=ExecutionTimingCoordinator(settings.reinforcement),
    )
    scheduler = PaperTradingScheduler(
        paper_trading_service=service,
        audit_store=store,
        alert_service=alert_service,
    )
    return store, scheduler


@pytest.mark.asyncio
async def test_scheduler_run_once_persists_job_and_run(tmp_path: Path) -> None:
    store, scheduler = _build_scheduler(tmp_path)
    await store.create_schema()

    job = await scheduler.create_job(
        PaperCycleJobCreate(
            symbol="BTC-USD",
            timeframe="1h",
            lookback_bars=600,
            interval_seconds=300,
            auto_start=False,
        )
    )
    cycle = await scheduler.run_job_once(job.id)
    runs = await scheduler.list_runs(job_id=job.id, limit=10)
    stored_job = await scheduler.get_job(job.id)

    assert cycle.symbol == "BTC-USD"
    assert stored_job is not None
    assert stored_job.last_status == "completed"
    assert len(runs) == 1
    assert runs[0].status == "completed"
    assert runs[0].job_id == job.id
    assert runs[0].cycle_payload is not None

    await scheduler.close()
    await store.close()


@pytest.mark.asyncio
async def test_scheduler_rejects_overlapping_cycles_for_same_symbol(tmp_path: Path) -> None:
    store, scheduler = _build_scheduler(tmp_path, delay_seconds=0.1)
    await store.create_schema()

    first = asyncio.create_task(
        scheduler.run_ad_hoc_cycle(symbol="BTC-USD", timeframe="1h", lookback_bars=600)
    )
    await asyncio.sleep(0.02)

    with pytest.raises(RuntimeError, match="already running"):
        await scheduler.run_ad_hoc_cycle(symbol="BTC-USD", timeframe="1h", lookback_bars=600)

    await first
    runs = await scheduler.list_runs(limit=10)

    assert len(runs) == 2
    assert {run.status for run in runs} == {"completed", "failed"}

    await scheduler.close()
    await store.close()
