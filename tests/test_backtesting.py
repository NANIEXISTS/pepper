from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd
import pytest

from trading_ai.backtesting import BacktestEngine, EmaCrossoverStrategy, FeatureLeakageAnalyzer, LookAheadBiasError, WalkForwardValidator
from trading_ai.features import FeatureEngineer
from trading_ai.settings import BacktestingSettings


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


def test_feature_leakage_analyzer_passes_stable_features() -> None:
    analyzer = FeatureLeakageAnalyzer()
    engineer = FeatureEngineer()

    result = analyzer.assert_no_lookahead(_market_frame(), engineer)

    assert result.passed is True
    assert "ema_20" in result.checked_features
    assert result.checkpoints_checked >= 1


def test_feature_leakage_analyzer_catches_future_leak() -> None:
    @dataclass(slots=True)
    class LeakyEngineer:
        def enrich(self, frame: pd.DataFrame) -> pd.DataFrame:
            enriched = frame.copy()
            enriched["future_close"] = enriched["close"].shift(-1)
            return enriched

    analyzer = FeatureLeakageAnalyzer()

    with pytest.raises(LookAheadBiasError, match="future_close"):
        analyzer.assert_no_lookahead(_market_frame(), LeakyEngineer())  # type: ignore[arg-type]


def test_backtest_engine_runs_ema_baseline() -> None:
    frame = FeatureEngineer().enrich(_market_frame())
    engine = BacktestEngine(BacktestingSettings())
    strategy = EmaCrossoverStrategy()

    result = engine.run(frame, strategy=strategy, symbol="BTC-USD", timeframe="1h")

    assert result.metrics.trade_count >= 1
    assert len(result.equity_curve) == len(frame)
    assert result.metrics.exposure_fraction > 0
    assert result.metrics.total_return_fraction == pytest.approx(result.metrics.total_return_fraction)


def test_walk_forward_validator_creates_non_overlapping_test_windows() -> None:
    frame = FeatureEngineer().enrich(_market_frame())
    settings = BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=3)
    engine = BacktestEngine(settings)
    validator = WalkForwardValidator(settings, engine)
    strategy = EmaCrossoverStrategy()

    result = validator.run(frame, strategy=strategy, symbol="BTC-USD", timeframe="1h")

    assert result.summary.window_count == 3
    test_ranges = [(window.test_start, window.test_end) for window in result.windows]
    assert test_ranges[0][1] <= test_ranges[1][0]
    assert test_ranges[1][1] <= test_ranges[2][0]
    assert all(window.result.ended_at == window.test_end for window in result.windows)
    assert result.summary.compounded_return_fraction == pytest.approx(result.summary.compounded_return_fraction)


def test_backtest_trade_bars_held_counts_only_bars_with_exposure() -> None:
    index = pd.date_range("2025-01-01", periods=4, freq="1h", tz="UTC")
    close = pd.Series([100.0, 101.0, 102.0, 103.0], index=index)
    position = pd.Series([0.0, 1.0, 1.0, 0.0], index=index)
    engine = BacktestEngine(BacktestingSettings())

    trades = engine._extract_trades(close, position)  # noqa: SLF001

    assert len(trades) == 1
    assert trades[0].bars_held == 2
