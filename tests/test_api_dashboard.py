from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from trading_ai.api.app import create_app
from trading_ai.settings import (
    BacktestingSettings,
    ExecutionSettings,
    LoggingSettings,
    PersistenceSettings,
    TradingSettings,
    TradingMode,
)


def _market_frame(rows: int = 600) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=rows, freq="1h", tz="UTC")
    close = [100 + (i * 0.03) + (5 * math.sin(i / 12)) for i in range(rows)]
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


def test_dashboard_route_serves_html(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module
    from trading_ai.data.service import MarketDataService

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'dashboard.db').as_posix()}"),
        execution=ExecutionSettings(),
        backtesting=BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=3),
        logging=LoggingSettings(level="INFO"),
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    async def fake_fetch_dataframe(self, request):  # noqa: ANN001
        return _market_frame(request.lookback_bars)

    monkeypatch.setattr(MarketDataService, "fetch_dataframe", fake_fetch_dataframe)

    with TestClient(create_app()) as client:
        response = client.get("/dashboard")

    assert response.status_code == 200
    assert "Pepper Operator Console" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_dashboard_data_route_returns_overview(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module
    from trading_ai.data.service import MarketDataService

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'dashboard-overview.db').as_posix()}"),
        execution=ExecutionSettings(),
        backtesting=BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=3),
        logging=LoggingSettings(level="INFO"),
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    async def fake_fetch_dataframe(self, request):  # noqa: ANN001
        return _market_frame(max(request.lookback_bars, 600))

    monkeypatch.setattr(MarketDataService, "fetch_dataframe", fake_fetch_dataframe)

    with TestClient(create_app()) as client:
        response = client.get("/dashboard/data?symbol=BTC-USD&timeframe=1h")

    assert response.status_code == 200
    payload = response.json()
    assert payload["config"]["mode"] == "paper"
    assert payload["market"]["symbol"] == "BTC-USD"
    assert len(payload["market"]["recent_bars"]) == 80
    assert "jobs" in payload
    assert "runs" in payload
    assert "trade_audit" in payload
    assert "venues" in payload
    assert "portfolio_breakdown" in payload
    assert "strategy_builder" in payload
    assert payload["backtest"]["leakage_check"]["passed"] is True
    assert "equity_curve" in payload["backtest"]
    assert "walk_forward_windows" in payload["backtest"]
    assert "trades" in payload["backtest"]
