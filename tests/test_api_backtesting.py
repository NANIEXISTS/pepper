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


def test_backtest_endpoint_returns_summary(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module
    from trading_ai.data.service import MarketDataService

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'api.db').as_posix()}"),
        execution=ExecutionSettings(),
        backtesting=BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=3),
        logging=LoggingSettings(level="INFO"),
    )

    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    async def fake_fetch_dataframe(self, request):  # noqa: ANN001
        return _market_frame(request.lookback_bars)

    monkeypatch.setattr(MarketDataService, "fetch_dataframe", fake_fetch_dataframe)

    with TestClient(create_app()) as client:
        response = client.get("/backtests/ema/BTC-USD?timeframe=1h&lookback_bars=600")

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "BTC-USD"
    assert payload["leakage_check"]["passed"] is True
    assert payload["backtest"]["strategy_name"].startswith("ema-crossover")
    assert payload["walk_forward"]["summary"]["window_count"] == 3


def test_paper_cycle_endpoint_returns_cycle(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module
    from trading_ai.data.service import MarketDataService

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'paper-api.db').as_posix()}"),
        execution=ExecutionSettings(),
        backtesting=BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=3),
        logging=LoggingSettings(level="INFO"),
    )

    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    async def fake_fetch_dataframe(self, request):  # noqa: ANN001
        return _market_frame(request.lookback_bars)

    monkeypatch.setattr(MarketDataService, "fetch_dataframe", fake_fetch_dataframe)

    with TestClient(create_app()) as client:
        response = client.post("/paper/cycles/BTC-USD?timeframe=1h&lookback_bars=600")

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "BTC-USD"
    assert payload["analysis"]["agent_name"] == "analyst-agent"
    assert payload["alert"] is not None
