from __future__ import annotations

import math

import pandas as pd
import pytest

from trading_ai.backtesting import (
    BacktestEngine,
    BollingerMeanReversionStrategy,
    EmaCrossoverStrategy,
    WalkForwardOptimizer,
)
from trading_ai.features import FeatureEngineer
from trading_ai.settings import BacktestingSettings


def _market_frame(rows: int = 800) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=rows, freq="1h", tz="UTC")
    close = [100 + (i * 0.04) + (8 * math.sin(i / 9)) for i in range(rows)]
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


def test_walk_forward_optimizer_selects_best_in_sample_per_window() -> None:
    frame = FeatureEngineer().enrich(_market_frame(rows=800))
    settings = BacktestingSettings(train_bars=240, test_bars=80, max_walk_forward_windows=3)
    engine = BacktestEngine(settings)
    optimizer = WalkForwardOptimizer(settings, engine)

    def factory(parameters: dict[str, float]) -> EmaCrossoverStrategy:
        return EmaCrossoverStrategy(
            short_window=int(parameters["fast_window"]),
            long_window=int(parameters["slow_window"]),
            trend_filter_window=200,
            long_only=True,
        )

    result = optimizer.optimize(
        frame,
        strategy_factory=factory,
        parameter_grid={"fast_window": [5, 10, 20], "slow_window": [40, 60]},
        symbol="BTC-USD",
        timeframe="1h",
        base_strategy_name="ema-baseline",
        selection_metric="sharpe_ratio",
    )

    assert result.summary.window_count >= 1
    assert result.summary.parameter_grid_size == 6
    assert result.summary.parameter_combinations_evaluated >= result.summary.window_count
    assert result.summary.parameter_combinations_evaluated <= 6 * result.summary.window_count
    assert result.windows
    for window in result.windows:
        assert window.selected_parameters["fast_window"] in {5, 10, 20}
        assert window.selected_parameters["slow_window"] in {40, 60}
        assert window.candidates_evaluated >= 1
        assert window.test_metrics.exposure_fraction >= 0.0
    assert result.leaderboard
    assert all(candidate.in_sample_metric == "sharpe_ratio" for candidate in result.leaderboard)
    # Stability score is bounded [0,1] and present per swept parameter
    assert set(result.summary.parameter_stability.keys()) == {"fast_window", "slow_window"}
    for value in result.summary.parameter_stability.values():
        assert 0.0 <= value <= 1.0


def test_walk_forward_optimizer_caps_combination_explosion() -> None:
    frame = FeatureEngineer().enrich(_market_frame(rows=600))
    settings = BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=2)
    engine = BacktestEngine(settings)
    optimizer = WalkForwardOptimizer(settings, engine)

    def factory(parameters: dict[str, float]) -> EmaCrossoverStrategy:
        return EmaCrossoverStrategy(
            short_window=int(parameters["fast_window"]),
            long_window=int(parameters["slow_window"]),
            trend_filter_window=200,
            long_only=True,
        )

    # 6 * 6 = 36 combos but max_combinations=8
    result = optimizer.optimize(
        frame,
        strategy_factory=factory,
        parameter_grid={
            "fast_window": [5, 10, 15, 20, 25, 30],
            "slow_window": [40, 50, 60, 70, 80, 90],
        },
        symbol="BTC-USD",
        timeframe="1h",
        base_strategy_name="ema-baseline",
        max_combinations=8,
    )

    assert result.summary.parameter_grid_size <= 8
    # Per-window evaluations are bounded by parameter_grid_size after capping
    for window in result.windows:
        assert window.candidates_evaluated <= 8


def test_walk_forward_optimizer_requires_grid() -> None:
    frame = FeatureEngineer().enrich(_market_frame(rows=400))
    settings = BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=1)
    engine = BacktestEngine(settings)
    optimizer = WalkForwardOptimizer(settings, engine)

    def factory(parameters: dict[str, float]) -> EmaCrossoverStrategy:
        return EmaCrossoverStrategy()

    with pytest.raises(ValueError, match="produced no candidates"):
        optimizer.optimize(
            frame,
            strategy_factory=factory,
            parameter_grid={"fast_window": []},
            symbol="BTC-USD",
            timeframe="1h",
            base_strategy_name="ema-baseline",
        )


def test_walk_forward_optimizer_rejects_short_history() -> None:
    frame = FeatureEngineer().enrich(_market_frame(rows=120))
    settings = BacktestingSettings(train_bars=200, test_bars=80, max_walk_forward_windows=1)
    engine = BacktestEngine(settings)
    optimizer = WalkForwardOptimizer(settings, engine)

    def factory(parameters: dict[str, float]) -> EmaCrossoverStrategy:
        return EmaCrossoverStrategy(short_window=int(parameters["fast_window"]))

    with pytest.raises(ValueError, match="Not enough bars"):
        optimizer.optimize(
            frame,
            strategy_factory=factory,
            parameter_grid={"fast_window": [10, 20]},
            symbol="BTC-USD",
            timeframe="1h",
            base_strategy_name="ema-baseline",
        )


def test_walk_forward_optimizer_works_with_bollinger_strategy() -> None:
    frame = FeatureEngineer().enrich(_market_frame(rows=800))
    settings = BacktestingSettings(train_bars=240, test_bars=80, max_walk_forward_windows=2)
    engine = BacktestEngine(settings)
    optimizer = WalkForwardOptimizer(settings, engine)

    def factory(parameters: dict[str, float]) -> BollingerMeanReversionStrategy:
        return BollingerMeanReversionStrategy(
            window=int(parameters["bollinger_window"]),
            band_multiplier=float(parameters["band_multiplier"]),
            trend_filter_window=200,
        )

    result = optimizer.optimize(
        frame,
        strategy_factory=factory,
        parameter_grid={
            "bollinger_window": [15, 20, 25],
            "band_multiplier": [1.5, 2.0, 2.5],
        },
        symbol="BTC-USD",
        timeframe="1h",
        base_strategy_name="bollinger-baseline",
        selection_metric="total_return_fraction",
    )

    assert result.windows
    assert result.summary.selection_metric == "total_return_fraction"
