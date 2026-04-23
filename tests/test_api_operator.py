from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from trading_ai.api.app import create_app
from trading_ai.persistence import TradeAuditStore
from trading_ai.portfolio import PortfolioService, Position
from trading_ai.settings import (
    BacktestingSettings,
    ExecutionSettings,
    LoggingSettings,
    PersistenceSettings,
    TradingSettings,
    TradingMode,
)


def _market_frame(symbol: str = "BTC-USD", rows: int = 600) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=rows, freq="1h", tz="UTC")
    close = [100 + (i * 0.03) + (5 * math.sin(i / 12)) for i in range(rows)]
    frame = pd.DataFrame(
        {
            "symbol": [symbol] * rows,
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


def test_app_restores_portfolio_state_on_startup(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module
    from trading_ai.data.service import MarketDataService

    db_path = tmp_path / "restored-portfolio.db"
    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}"),
        execution=ExecutionSettings(),
        backtesting=BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=3),
        logging=LoggingSettings(level="INFO"),
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    async def fake_fetch_dataframe(self, request):  # noqa: ANN001
        return _market_frame(request.symbol, max(request.lookback_bars, 600))

    monkeypatch.setattr(MarketDataService, "fetch_dataframe", fake_fetch_dataframe)

    store = TradeAuditStore.from_database_url(settings.persistence.database_url)
    portfolio = PortfolioService(starting_cash=settings.paper_trading.starting_cash)
    portfolio.cash = 9_500.0
    portfolio.realized_pnl = -25.0
    portfolio.positions["BTC-USD"] = Position(
        symbol="BTC-USD",
        quantity=0.5,
        average_entry_price=100.0,
        last_price=105.0,
    )
    import asyncio
    asyncio.run(store.create_schema())
    asyncio.run(store.save_portfolio_state(portfolio.export_state()))
    asyncio.run(store.close())

    with TestClient(create_app()) as client:
        response = client.get("/portfolio")

    assert response.status_code == 200
    payload = response.json()
    assert payload["cash"] == 9500.0
    assert "BTC-USD" in payload["positions"]


def test_manual_paper_order_updates_portfolio_and_audit(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module
    from trading_ai.data.service import MarketDataService

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'manual-order.db').as_posix()}"),
        execution=ExecutionSettings(),
        backtesting=BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=3),
        logging=LoggingSettings(level="INFO"),
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    async def fake_fetch_dataframe(self, request):  # noqa: ANN001
        return _market_frame(request.symbol, max(request.lookback_bars, 600))

    monkeypatch.setattr(MarketDataService, "fetch_dataframe", fake_fetch_dataframe)

    with TestClient(create_app()) as client:
        order_response = client.post(
            "/paper/orders/manual",
            json={
                "symbol": "BTC-USD",
                "timeframe": "1h",
                "side": "buy",
                "quantity": 0.1,
                "stop_loss_price": 95.0,
            },
        )
        assert order_response.status_code == 200
        order_payload = order_response.json()
        assert order_payload["report"]["status"] == "filled"
        assert "BTC-USD" in order_payload["portfolio"]["positions"]

        audit_response = client.get("/audit/trades?limit=5")
        assert audit_response.status_code == 200
        events = audit_response.json()["events"]
        assert len(events) == 1
        assert events[0]["symbol"] == "BTC-USD"

        dashboard_response = client.get("/dashboard/data?symbol=BTC-USD&timeframe=1h")
        assert dashboard_response.status_code == 200
        dashboard_payload = dashboard_response.json()
        assert len(dashboard_payload["trade_audit"]) == 1


def test_manual_paper_order_rejects_stale_market_data(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module
    from trading_ai.data.service import MarketDataService

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'manual-order-stale.db').as_posix()}"),
        execution=ExecutionSettings(),
        backtesting=BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=3),
        logging=LoggingSettings(level="INFO"),
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    async def stale_fetch_dataframe(self, request):  # noqa: ANN001
        frame = _market_frame(request.symbol, max(request.lookback_bars, 600))
        frame.attrs["stale"] = True
        frame.attrs["cache_age_seconds"] = 120.0
        return frame

    monkeypatch.setattr(MarketDataService, "fetch_dataframe", stale_fetch_dataframe)

    with TestClient(create_app()) as client:
        order_response = client.post(
            "/paper/orders/manual",
            json={
                "symbol": "BTC-USD",
                "timeframe": "1h",
                "side": "buy",
                "quantity": 0.1,
                "stop_loss_price": 95.0,
            },
        )

    assert order_response.status_code == 503
    assert "requires fresh market data" in order_response.json()["detail"]
