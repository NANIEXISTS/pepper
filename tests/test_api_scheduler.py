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


def test_paper_job_endpoints_create_run_and_list_history(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module
    from trading_ai.data.service import MarketDataService

    settings = TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'paper-jobs.db').as_posix()}"),
        execution=ExecutionSettings(),
        backtesting=BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=3),
        logging=LoggingSettings(level="INFO"),
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    async def fake_fetch_dataframe(self, request):  # noqa: ANN001
        return _market_frame(max(request.lookback_bars, 600))

    monkeypatch.setattr(MarketDataService, "fetch_dataframe", fake_fetch_dataframe)

    with TestClient(create_app()) as client:
        create_response = client.post(
            "/paper/jobs",
            json={
                "symbol": "BTC-USD",
                "timeframe": "1h",
                "lookback_bars": 600,
                "interval_seconds": 300,
                "auto_start": False,
            },
        )
        assert create_response.status_code == 200
        job = create_response.json()["job"]

        run_response = client.post(f"/paper/jobs/{job['id']}/run")
        assert run_response.status_code == 200
        assert run_response.json()["symbol"] == "BTC-USD"

        list_jobs = client.get("/paper/jobs")
        assert list_jobs.status_code == 200
        assert len(list_jobs.json()["jobs"]) == 1

        list_runs = client.get(f"/paper/runs?job_id={job['id']}&limit=10")
        assert list_runs.status_code == 200
        runs = list_runs.json()["runs"]
        assert len(runs) == 1
        assert runs[0]["status"] == "completed"

        start_response = client.post(f"/paper/jobs/{job['id']}/start")
        assert start_response.status_code == 200
        assert start_response.json()["job"]["is_active"] is True

        pause_response = client.post(f"/paper/jobs/{job['id']}/pause")
        assert pause_response.status_code == 200
        assert pause_response.json()["job"]["is_active"] is False
