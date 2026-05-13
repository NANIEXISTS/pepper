from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True)
class BollingerMeanReversionStrategy:
    """Mean-reversion using rolling Bollinger bands.

    Enters long when the close drops below the lower band; exits when the close
    reverts to (or above) the rolling mean. Symmetric short entries are off by
    default - flip ``long_only`` to enable them. The trend filter, when on,
    refuses longs below the slow trend EMA so we are not catching falling
    knives during regime breaks.
    """

    window: int = 20
    band_multiplier: float = 2.0
    trend_filter_window: int = 200
    long_only: bool = True
    require_bullish_trend: bool = False

    @property
    def name(self) -> str:
        suffix = "-trend" if self.require_bullish_trend else ""
        return f"bollinger-meanrev-{self.window}-{self.band_multiplier:.2f}{suffix}"

    def generate_target_position(self, frame: pd.DataFrame) -> pd.Series:
        self._validate(frame)
        close = frame["close"]
        rolling_mean = close.rolling(self.window).mean()
        rolling_std = close.rolling(self.window).std(ddof=0)
        upper = rolling_mean + (rolling_std * self.band_multiplier)
        lower = rolling_mean - (rolling_std * self.band_multiplier)
        trend = close.ewm(span=self.trend_filter_window, adjust=False).mean()

        target = pd.Series(0.0, index=frame.index, dtype="float64")
        in_long = False
        in_short = False
        closes = close.to_numpy()
        mids = rolling_mean.to_numpy()
        ups = upper.to_numpy()
        los = lower.to_numpy()
        trends = trend.to_numpy()
        out = target.to_numpy().copy()

        for i in range(len(frame)):
            mid = mids[i]
            up = ups[i]
            lo = los[i]
            if pd.isna(mid) or pd.isna(up) or pd.isna(lo):
                continue
            close_value = closes[i]
            trend_value = trends[i]
            if in_long:
                if close_value >= mid:
                    in_long = False
                else:
                    out[i] = 1.0
            elif in_short:
                if close_value <= mid:
                    in_short = False
                else:
                    out[i] = -1.0
            else:
                long_ok = close_value < lo and (
                    not self.require_bullish_trend or close_value >= trend_value
                )
                short_ok = (
                    not self.long_only
                    and close_value > up
                    and (not self.require_bullish_trend or close_value <= trend_value)
                )
                if long_ok:
                    in_long = True
                    out[i] = 1.0
                elif short_ok:
                    in_short = True
                    out[i] = -1.0

        return pd.Series(out, index=frame.index, dtype="float64")

    def _validate(self, frame: pd.DataFrame) -> None:
        if "close" not in frame.columns:
            raise ValueError("Bollinger mean-reversion strategy requires a close column.")
        if len(frame) < self.window:
            raise ValueError("Not enough bars for the Bollinger window.")
        if not isinstance(frame.index, pd.DatetimeIndex):
            raise ValueError("Strategy requires a DatetimeIndex.")
        if frame.index.tz is None:
            raise ValueError("Strategy requires timezone-aware timestamps.")
        if not frame.index.is_monotonic_increasing:
            raise ValueError("Strategy requires time-ordered data.")
        if self.band_multiplier <= 0:
            raise ValueError("Bollinger band multiplier must be positive.")
