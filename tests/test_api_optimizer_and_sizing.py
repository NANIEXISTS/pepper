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
    TradingMode,
    TradingSettings,
)


def _market_frame(rows: int = 800) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=rows, freq="1h", tz="UTC")
    close = [100 + (i * 0.04) + (5 * math.sin(i / 11)) for i in range(rows)]
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


def _settings(tmp_path: Path) -> TradingSettings:
    return TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'optimize.db').as_posix()}"),
        execution=ExecutionSettings(),
        backtesting=BacktestingSettings(train_bars=240, test_bars=80, max_walk_forward_windows=3),
        logging=LoggingSettings(level="INFO"),
    )


def _patch_market_data(monkeypatch) -> None:
    from trading_ai.data.service import MarketDataService

    async def fake_fetch_dataframe(self, request):  # noqa: ANN001
        return _market_frame(max(request.lookback_bars, 800))

    monkeypatch.setattr(MarketDataService, "fetch_dataframe", fake_fetch_dataframe)


def test_optimize_endpoint_runs_walk_forward_grid(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = _settings(tmp_path)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    _patch_market_data(monkeypatch)

    base_prompt = "Buy when EMA 20 crosses above EMA 50, only when price is above EMA 200, with stop loss 3%."
    with TestClient(create_app()) as client:
        draft = client.post("/strategies/draft", json={"prompt": base_prompt})
        assert draft.status_code == 200
        graph = draft.json()["graph"]

        response = client.post(
            "/strategies/optimize",
            json={
                "symbol": "BTC-USD",
                "timeframe": "1h",
                "lookback_bars": 800,
                "base_graph": graph,
                "parameter_grid": {
                    "fast_window": [10, 20, 30],
                    "slow_window": [50, 80],
                },
                "selection_metric": "sharpe_ratio",
                "max_combinations": 12,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["leakage_check"]["passed"] is True
    optimization = payload["optimization"]
    assert optimization["summary"]["window_count"] >= 1
    assert optimization["summary"]["parameter_grid_size"] == 6
    assert optimization["summary"]["selection_metric"] == "sharpe_ratio"
    assert optimization["windows"]
    for window in optimization["windows"]:
        assert window["selected_parameters"]["fast_window"] in [10, 20, 30]
        assert window["selected_parameters"]["slow_window"] in [50, 80]
    assert optimization["leaderboard"]


def test_optimize_endpoint_rejects_empty_grid(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = _settings(tmp_path)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    _patch_market_data(monkeypatch)

    base_prompt = "Buy when EMA 20 crosses above EMA 50, only when price is above EMA 200, with stop loss 3%."
    with TestClient(create_app()) as client:
        draft = client.post("/strategies/draft", json={"prompt": base_prompt})
        graph = draft.json()["graph"]

        response = client.post(
            "/strategies/optimize",
            json={
                "symbol": "BTC-USD",
                "base_graph": graph,
                "parameter_grid": {},
            },
        )

    assert response.status_code == 422


def test_optimize_endpoint_rejects_unknown_grid_keys(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = _settings(tmp_path)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    _patch_market_data(monkeypatch)

    base_prompt = "Buy when EMA 20 crosses above EMA 50, only when price is above EMA 200, with stop loss 3%."
    with TestClient(create_app()) as client:
        draft = client.post("/strategies/draft", json={"prompt": base_prompt})
        graph = draft.json()["graph"]

        response = client.post(
            "/strategies/optimize",
            json={
                "symbol": "BTC-USD",
                "base_graph": graph,
                "parameter_grid": {"unknown_key": [1, 2, 3]},
            },
        )

    assert response.status_code == 422


def test_risk_size_endpoint_returns_position(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = _settings(tmp_path)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    _patch_market_data(monkeypatch)

    with TestClient(create_app()) as client:
        response = client.post(
            "/risk/size",
            json={
                "equity": 100_000.0,
                "entry_price": 100.0,
                "stop_loss_price": 98.0,
                "atr": 2.0,
                "available_cash": 50_000.0,
                "mode": "volatility_targeted",
                "target_daily_volatility_fraction": 0.005,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "volatility_targeted"
    assert payload["quantity"] > 0
    assert payload["binding_constraint"] in (
        "stop_loss_risk",
        "available_cash",
        "volatility_target",
        "no_capacity",
    )


def test_paper_orders_endpoint_now_validates_schema(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = _settings(tmp_path)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    _patch_market_data(monkeypatch)

    with TestClient(create_app()) as client:
        # Pre-Pydantic shape (raw dict missing fields) should now be rejected with 422
        bad = client.post("/orders/paper", json={"order": {}, "portfolio": {}})
        assert bad.status_code == 422

        good = client.post(
            "/orders/paper",
            json={
                "order": {
                    "symbol": "BTC-USD",
                    "side": "buy",
                    "quantity": 0.01,
                    "entry_price": 100.0,
                    "stop_loss_price": 99.0,
                },
                "portfolio": {"equity": 100_000.0, "cash": 100_000.0},
                "agent_name": "tests",
                "signal": "BUY",
                "confidence": 0.6,
                "rationale": "Sanity test order",
            },
        )
        assert good.status_code == 200
        report = good.json()
        assert report["status"] in {"filled", "rejected"}
        assert report["router"] == "paper"


def test_audit_trail_records_in_dev_mode(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = _settings(tmp_path)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    _patch_market_data(monkeypatch)

    with TestClient(create_app()) as client:
        client.post("/readiness/drawdown-breaker/selftest")
        events = client.get("/audit/operators").json()["events"]

    actions = [event["action"] for event in events]
    assert "run_drawdown_breaker_selftest" in actions
    relevant = next(event for event in events if event["action"] == "run_drawdown_breaker_selftest")
    assert relevant["details_payload"].get("auth_enabled") is False
    assert relevant["username"] == "local-dev"
