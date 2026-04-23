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


def _market_frame(rows: int = 700) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=rows, freq="1h", tz="UTC")
    close = [100 + (i * 0.04) + (4 * math.sin(i / 11)) for i in range(rows)]
    frame = pd.DataFrame(
        {
            "symbol": ["BTC-USD"] * rows,
            "timeframe": ["1h"] * rows,
            "open": [price - 0.2 for price in close],
            "high": [price + 0.4 for price in close],
            "low": [price - 0.6 for price in close],
            "close": close,
            "volume": [1000 + (i % 11) * 40 for i in range(rows)],
        },
        index=index,
    )
    frame.index.name = "timestamp"
    return frame


def test_strategy_builder_endpoints(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module
    from trading_ai.data.service import MarketDataService

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'strategy-api.db').as_posix()}"),
        execution=ExecutionSettings(),
        backtesting=BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=3),
        logging=LoggingSettings(level="INFO"),
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    async def fake_fetch_dataframe(self, request):  # noqa: ANN001
        return _market_frame(max(request.lookback_bars, 700))

    monkeypatch.setattr(MarketDataService, "fetch_dataframe", fake_fetch_dataframe)

    prompt = "Buy when EMA 20 crosses above EMA 50, only when price is above EMA 200 and RSI 14 is below 70, with stop loss 3%."

    with TestClient(create_app()) as client:
        draft_response = client.post("/strategies/draft", json={"prompt": prompt})
        assert draft_response.status_code == 200
        draft_payload = draft_response.json()
        assert draft_payload["validation"]["passed"] is True
        assert draft_payload["graph"]["name"].startswith("EMA 20/50")

        validate_response = client.post("/strategies/validate", json={"graph": draft_payload["graph"]})
        assert validate_response.status_code == 200
        assert validate_response.json()["passed"] is True

        backtest_response = client.post(
            "/strategies/backtests",
            json={
                "symbol": "BTC-USD",
                "timeframe": "1h",
                "lookback_bars": 700,
                "graph": draft_payload["graph"],
            },
        )
        assert backtest_response.status_code == 200
        backtest_payload = backtest_response.json()
        assert backtest_payload["validation"]["passed"] is True
        assert backtest_payload["leakage_check"]["passed"] is True
        assert backtest_payload["backtest"]["strategy_name"].startswith("ema-crossover-20-50")
        assert backtest_payload["walk_forward"]["summary"]["window_count"] == 3


def test_venue_capabilities_and_live_gate_endpoints(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'venue-api.db').as_posix()}"),
        execution=ExecutionSettings(live_router="alpaca"),
        logging=LoggingSettings(level="INFO"),
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    with TestClient(create_app()) as client:
        venue_response = client.get("/venues/capabilities")
        readiness_response = client.get("/readiness/live-gate")

    assert venue_response.status_code == 200
    venue_payload = venue_response.json()
    assert venue_payload["configured_live_router"] == "alpaca"
    assert any(venue["venue_id"] == "alpaca-market-data" for venue in venue_payload["venues"])

    assert readiness_response.status_code == 200
    readiness_payload = readiness_response.json()
    assert readiness_payload["runbook_documented"] is True
    assert readiness_payload["live_trading_enabled"] is False
