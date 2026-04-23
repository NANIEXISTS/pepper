from __future__ import annotations

import pandas as pd
import pytest

from trading_ai.features import FeatureEngineer


def _sample_frame() -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=260, freq="1h", tz="UTC")
    rows = len(index)
    frame = pd.DataFrame(
        {
            "symbol": ["BTC-USD"] * rows,
            "timeframe": ["1h"] * rows,
            "open": [100 + i * 0.1 for i in range(rows)],
            "high": [101 + i * 0.1 for i in range(rows)],
            "low": [99 + i * 0.1 for i in range(rows)],
            "close": [100 + i * 0.12 for i in range(rows)],
            "volume": [1000 + (i % 20) * 25 for i in range(rows)],
        },
        index=index,
    )
    frame.index.name = "timestamp"
    return frame


def test_feature_engineer_enriches_happy_path() -> None:
    engineer = FeatureEngineer()

    enriched = engineer.enrich(_sample_frame())

    assert "ema_20" in enriched.columns
    assert "rsi_14" in enriched.columns
    assert "atr_14" in enriched.columns
    assert enriched.index.is_monotonic_increasing
    assert pd.notna(enriched["ema_20"].iloc[-1])


def test_feature_engineer_rejects_missing_column() -> None:
    engineer = FeatureEngineer()
    malformed = _sample_frame().drop(columns=["high"])

    with pytest.raises(ValueError, match="Missing required columns"):
        engineer.enrich(malformed)
