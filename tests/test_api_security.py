from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from trading_ai.api.app import create_app
from trading_ai.data.exceptions import MarketDataUnavailableError
from trading_ai.settings import (
    AuthSettings,
    BacktestingSettings,
    ExecutionSettings,
    LoggingSettings,
    OperatorAccountSettings,
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


def _settings(tmp_path: Path) -> TradingSettings:
    return TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'security.db').as_posix()}"),
        execution=ExecutionSettings(),
        backtesting=BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=3),
        logging=LoggingSettings(level="INFO"),
        auth=AuthSettings(
            enabled=True,
            operators=[
                OperatorAccountSettings(username="viewer01", password="viewerpass1", role="viewer"),
                OperatorAccountSettings(username="trader01", password="traderpass1", role="trader"),
                OperatorAccountSettings(username="admin01", password="adminpass1", role="admin"),
            ],
        ),
    )


def test_authentication_and_role_checks_gate_operator_endpoints(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module
    from trading_ai.data.service import MarketDataService

    settings = _settings(tmp_path)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    async def fake_fetch_dataframe(self, request):  # noqa: ANN001
        return _market_frame(request.symbol, max(request.lookback_bars, 600))

    monkeypatch.setattr(MarketDataService, "fetch_dataframe", fake_fetch_dataframe)

    with TestClient(create_app()) as client:
        unauthorized = client.get("/config")
        assert unauthorized.status_code == 401

        viewer_response = client.get("/config", auth=("viewer01", "viewerpass1"))
        assert viewer_response.status_code == 200
        assert viewer_response.json()["auth_enabled"] is True

        forbidden = client.post(
            "/paper/jobs",
            auth=("viewer01", "viewerpass1"),
            json={
                "symbol": "BTC-USD",
                "timeframe": "1h",
                "lookback_bars": 600,
                "interval_seconds": 300,
                "auto_start": False,
            },
        )
        assert forbidden.status_code == 403

        trader_create = client.post(
            "/paper/jobs",
            auth=("trader01", "traderpass1"),
            json={
                "symbol": "BTC-USD",
                "timeframe": "1h",
                "lookback_bars": 600,
                "interval_seconds": 300,
                "auto_start": False,
            },
        )
        assert trader_create.status_code == 200

        audit_response = client.get("/audit/operators?limit=10", auth=("admin01", "adminpass1"))
        assert audit_response.status_code == 200
        events = audit_response.json()["events"]
        assert any(event["action"] == "authenticate" and event["outcome"] == "rejected" for event in events)
        assert any(event["action"] == "authorize" and event["outcome"] == "forbidden" for event in events)
        assert any(event["action"] == "create_paper_job" and event["outcome"] == "success" for event in events)


def test_market_data_endpoint_returns_503_when_no_provider_or_cache_is_available(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module
    from trading_ai.data.service import MarketDataService

    settings = _settings(tmp_path)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    async def unavailable(self, request):  # noqa: ANN001
        raise MarketDataUnavailableError(
            symbol=request.symbol,
            timeframe=request.timeframe,
            failures=["ccxt: upstream unavailable", "yahoo: no bars returned"],
        )

    monkeypatch.setattr(MarketDataService, "fetch_dataframe", unavailable)

    with TestClient(create_app()) as client:
        response = client.get("/market-data/BTC-USD?timeframe=1h", auth=("viewer01", "viewerpass1"))

    assert response.status_code == 503
    assert "Market data unavailable for BTC-USD 1h" in response.json()["detail"]
