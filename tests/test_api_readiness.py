from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from trading_ai.api.app import create_app
from trading_ai.persistence import TradeAuditStore
from trading_ai.persistence.models import PaperCycleRunRecord
from trading_ai.settings import (
    BacktestingSettings,
    ExecutionSettings,
    LiveReadinessSettings,
    LoggingSettings,
    PersistenceSettings,
    TradingMode,
    TradingSettings,
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


def _base_settings(tmp_path: Path, *, live_enabled: bool = False) -> TradingSettings:
    db_path = tmp_path / "readiness.db"
    return TradingSettings(
        app_mode=TradingMode.PAPER,
        persistence=PersistenceSettings(database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}"),
        execution=ExecutionSettings(live_trading_enabled=live_enabled),
        backtesting=BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=3),
        logging=LoggingSettings(level="INFO"),
        live_readiness=LiveReadinessSettings(),
    )


def _patch_market_data(monkeypatch) -> None:
    from trading_ai.data.service import MarketDataService

    async def fake_fetch_dataframe(self, request):  # noqa: ANN001
        return _market_frame(request.symbol, max(request.lookback_bars, 600))

    monkeypatch.setattr(MarketDataService, "fetch_dataframe", fake_fetch_dataframe)


def _seed_completed_burn_in_runs(database_url: str, days: int) -> None:
    async def _seed() -> None:
        store = TradeAuditStore.from_database_url(database_url)
        await store.create_schema()
        async with store.session_factory() as session:
            base = datetime.now(UTC) - timedelta(days=days)
            for day_offset in range(days):
                started_at = base + timedelta(days=day_offset)
                finished_at = started_at + timedelta(minutes=5)
                session.add(
                    PaperCycleRunRecord(
                        job_id=None,
                        source="test-seed",
                        symbol="BTC-USD",
                        timeframe="1h",
                        started_at=started_at,
                        finished_at=finished_at,
                        status="completed",
                        execution_status="filled",
                        trade_executed=True,
                        error_message=None,
                        cycle_payload={
                            "portfolio": {
                                "equity": 100_000 + (day_offset * 100),
                                "cash": 100_000 + (day_offset * 100),
                                "daily_pnl_fraction": 0.001,
                                "positions": {},
                                "stale_symbols": [],
                                "updated_at": finished_at.isoformat(),
                            }
                        },
                    )
                )
            await session.commit()
        await store.close()

    asyncio.run(_seed())


def test_live_gate_summary_lists_blocking_reasons_for_empty_state(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = _base_settings(tmp_path)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    _patch_market_data(monkeypatch)

    with TestClient(create_app()) as client:
        response = client.get("/readiness/live-gate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_capital_allowed"] is False
    reasons = set(payload["blocking_reasons"])
    assert "credential_audit_missing_or_stale" in reasons
    assert "drawdown_breaker_selftest_missing_or_stale" in reasons
    assert "ramp_plan_not_recorded" in reasons
    assert "live_trading_disabled_by_config" in reasons
    assert any(reason.startswith("paper_burn_in_incomplete") for reason in reasons)
    assert payload["required_burn_in_days"] == 28


def test_drawdown_breaker_selftest_passes_with_default_risk_config(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = _base_settings(tmp_path)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    _patch_market_data(monkeypatch)

    with TestClient(create_app()) as client:
        response = client.post("/readiness/drawdown-breaker/selftest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["passed"] is True
    assert payload["result"]["circuit_breaker_triggered"] is True
    assert payload["summary"]["drawdown_breaker_selftest_passed"] is True
    assert payload["summary"]["drawdown_breaker_selftest_fresh"] is True
    assert "drawdown_breaker_selftest_missing_or_stale" not in payload["summary"]["blocking_reasons"]


def test_credential_audit_attestation_flows_into_summary(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = _base_settings(tmp_path)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    _patch_market_data(monkeypatch)

    with TestClient(create_app()) as client:
        response = client.post(
            "/readiness/credential-audit",
            json={
                "venue": "alpaca",
                "scope": "trade",
                "auditor": "ops-lead",
                "notes": "Permissions limited to trade; no withdraw.",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["attestation"]["kind"] == "credential_audit"
    assert payload["summary"]["credential_audit_fresh"] is True
    assert payload["summary"]["credential_audit"]["payload"]["venue"] == "alpaca"


def test_ramp_plan_attestation_enforces_cap(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = _base_settings(tmp_path)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    _patch_market_data(monkeypatch)

    with TestClient(create_app()) as client:
        too_large = client.post(
            "/readiness/ramp-plan",
            json={
                "target_venue": "alpaca",
                "capital_cap_fraction": 0.5,
                "notes": "Attempting to bypass cap",
            },
        )
        assert too_large.status_code == 422

        accepted = client.post(
            "/readiness/ramp-plan",
            json={
                "target_venue": "alpaca",
                "capital_cap_fraction": 0.005,
                "notes": "First capital ramp at 0.5% of target.",
            },
        )
        assert accepted.status_code == 200
        payload = accepted.json()
        assert payload["summary"]["ramp_plan_recorded"] is True
        assert payload["summary"]["ramp_plan_within_cap"] is True


def test_paper_profitability_endpoint_reports_14_day_profit(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = _base_settings(tmp_path)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    _patch_market_data(monkeypatch)
    _seed_completed_burn_in_runs(settings.persistence.database_url, days=14)

    with TestClient(create_app()) as client:
        response = client.get("/readiness/paper-profitability")

    assert response.status_code == 200
    payload = response.json()
    assert payload["required_days"] == 14
    assert payload["complete"] is True
    assert payload["passed"] is True
    assert payload["status"] == "profitable"
    assert payload["total_return_fraction"] > 0
    assert len(payload["days"]) == 14


def test_live_capital_allowed_only_when_all_gates_pass(monkeypatch, tmp_path: Path) -> None:
    from trading_ai.api import app as app_module

    settings = _base_settings(tmp_path, live_enabled=True)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    _patch_market_data(monkeypatch)

    _seed_completed_burn_in_runs(settings.persistence.database_url, days=28)

    with TestClient(create_app()) as client:
        # Burn-in alone is insufficient.
        initial = client.get("/readiness/live-gate")
        assert initial.status_code == 200
        assert initial.json()["twenty_eight_day_gate_passed"] is True
        assert initial.json()["fourteen_day_profitability_passed"] is True
        assert initial.json()["live_capital_allowed"] is False

        # Record drawdown selftest.
        selftest = client.post("/readiness/drawdown-breaker/selftest")
        assert selftest.status_code == 200
        assert selftest.json()["summary"]["live_capital_allowed"] is False

        # Record credential audit.
        audit = client.post(
            "/readiness/credential-audit",
            json={
                "venue": "alpaca",
                "scope": "trade",
                "auditor": "ops-lead",
            },
        )
        assert audit.status_code == 200
        assert audit.json()["summary"]["live_capital_allowed"] is False

        # Record ramp plan within cap.
        ramp = client.post(
            "/readiness/ramp-plan",
            json={
                "target_venue": "alpaca",
                "capital_cap_fraction": 0.005,
            },
        )
        assert ramp.status_code == 200
        final = ramp.json()["summary"]
        assert final["live_capital_allowed"] is True
        assert final["blocking_reasons"] == []

        history = client.get("/readiness/history?limit=10")
        assert history.status_code == 200
        kinds = {event["kind"] for event in history.json()["events"]}
        assert {"credential_audit", "drawdown_breaker_selftest", "ramp_plan"}.issubset(kinds)
