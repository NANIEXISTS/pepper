from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True)
class EmaCrossoverStrategy:
    short_window: int = 20
    long_window: int = 50
    trend_filter_window: int = 200
    long_only: bool = True

    @property
    def name(self) -> str:
        return f"ema-crossover-{self.short_window}-{self.long_window}"

    def generate_target_position(self, frame: pd.DataFrame) -> pd.Series:
        self._validate(frame)
        close = frame["close"]
        fast = close.ewm(span=self.short_window, adjust=False).mean()
        slow = close.ewm(span=self.long_window, adjust=False).mean()
        trend = close.ewm(span=self.trend_filter_window, adjust=False).mean()

        long_condition = (fast > slow) & (close >= trend)
        target = pd.Series(0.0, index=frame.index, dtype="float64")
        target.loc[long_condition] = 1.0

        if not self.long_only:
            short_condition = (fast < slow) & (close < trend)
            target.loc[short_condition] = -1.0

        return target

    def _validate(self, frame: pd.DataFrame) -> None:
        if "close" not in frame.columns:
            raise ValueError("EMA crossover strategy requires a close column.")
        if len(frame) < self.long_window:
            raise ValueError("Not enough bars to evaluate the long EMA window.")
        if not isinstance(frame.index, pd.DatetimeIndex):
            raise ValueError("Strategy requires a DatetimeIndex.")
        if frame.index.tz is None:
            raise ValueError("Strategy requires timezone-aware timestamps.")
        if not frame.index.is_monotonic_increasing:
            raise ValueError("Strategy requires time-ordered data.")
