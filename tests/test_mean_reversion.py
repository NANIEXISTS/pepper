from __future__ import annotations

import math

import pandas as pd
import pytest

from trading_ai.backtesting import BacktestEngine, BollingerMeanReversionStrategy
from trading_ai.features import FeatureEngineer
from trading_ai.settings import BacktestingSettings


def _oscillating_frame(rows: int = 300) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=rows, freq="1h", tz="UTC")
    # Pure oscillation, no drift - mean reversion should thrive here
    close = [100 + (10 * math.sin(i / 8)) for i in range(rows)]
    frame = pd.DataFrame(
        {
            "symbol": ["BTC-USD"] * rows,
            "timeframe": ["1h"] * rows,
            "open": [price - 0.1 for price in close],
            "high": [price + 0.4 for price in close],
            "low": [price - 0.4 for price in close],
            "close": close,
            "volume": [1000.0] * rows,
        },
        index=index,
    )
    frame.index.name = "timestamp"
    return frame


def test_bollinger_strategy_emits_long_only_positions_by_default() -> None:
    frame = _oscillating_frame()
    strategy = BollingerMeanReversionStrategy(window=20, band_multiplier=2.0)
    target = strategy.generate_target_position(frame)

    assert (target >= 0).all(), "long_only=True should never go negative"
    assert (target <= 1.0).all()
    assert target.sum() > 0, "Mean reversion should take some long entries on a sine wave"


def test_bollinger_strategy_can_short_when_long_only_disabled() -> None:
    frame = _oscillating_frame()
    strategy = BollingerMeanReversionStrategy(window=20, band_multiplier=2.0, long_only=False)
    target = strategy.generate_target_position(frame)

    assert (target == -1.0).any(), "Disabling long_only should allow short entries"
    assert (target == 1.0).any()


def test_bollinger_strategy_validates_inputs() -> None:
    strategy = BollingerMeanReversionStrategy(window=20, band_multiplier=2.0)
    bad_frame = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "volume": [1.0]})
    with pytest.raises(ValueError, match="close column"):
        strategy.generate_target_position(bad_frame)


def test_bollinger_strategy_runs_through_backtest_engine() -> None:
    frame = FeatureEngineer().enrich(_oscillating_frame(rows=400))
    engine = BacktestEngine(BacktestingSettings())
    strategy = BollingerMeanReversionStrategy(window=20, band_multiplier=2.0)

    result = engine.run(frame, strategy=strategy, symbol="BTC-USD", timeframe="1h")

    assert result.metrics.trade_count >= 1
    assert "bollinger-meanrev" in result.strategy_name
