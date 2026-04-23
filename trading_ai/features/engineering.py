from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True)
class FeatureEngineer:
    required_columns: tuple[str, ...] = ("open", "high", "low", "close", "volume")

    def enrich(self, frame: pd.DataFrame) -> pd.DataFrame:
        self._validate(frame)
        enriched = frame.copy()

        close = enriched["close"]
        high = enriched["high"]
        low = enriched["low"]
        volume = enriched["volume"]

        enriched["ema_20"] = close.ewm(span=20, adjust=False).mean()
        enriched["ema_50"] = close.ewm(span=50, adjust=False).mean()
        enriched["ema_200"] = close.ewm(span=200, adjust=False).mean()

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(window=14).mean()
        loss = (-delta.clip(upper=0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, pd.NA)
        enriched["rsi_14"] = 100 - (100 / (1 + rs))

        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        enriched["macd"] = ema_fast - ema_slow
        enriched["macd_signal"] = enriched["macd"].ewm(span=9, adjust=False).mean()
        enriched["macd_histogram"] = enriched["macd"] - enriched["macd_signal"]

        rolling_mean = close.rolling(window=20).mean()
        rolling_std = close.rolling(window=20).std()
        enriched["bb_mid"] = rolling_mean
        enriched["bb_upper"] = rolling_mean + (rolling_std * 2)
        enriched["bb_lower"] = rolling_mean - (rolling_std * 2)

        previous_close = close.shift(1)
        true_range = pd.concat(
            [
                high - low,
                (high - previous_close).abs(),
                (low - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        enriched["atr_14"] = true_range.rolling(window=14).mean()
        enriched["volume_zscore_20"] = (volume - volume.rolling(20).mean()) / volume.rolling(20).std()

        return enriched

    def _validate(self, frame: pd.DataFrame) -> None:
        missing_columns = [column for column in self.required_columns if column not in frame.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        if not isinstance(frame.index, pd.DatetimeIndex):
            raise ValueError("Feature engineering requires a DatetimeIndex.")
        if frame.index.tz is None:
            raise ValueError("Feature engineering requires timezone-aware timestamps.")
        if not frame.index.is_monotonic_increasing:
            raise ValueError("Feature engineering requires time-ordered data.")
        if frame.index.has_duplicates:
            raise ValueError("Feature engineering rejects duplicate timestamps.")
        if frame[list(self.required_columns)].isnull().all().any():
            raise ValueError("Feature engineering found a fully empty required column.")
