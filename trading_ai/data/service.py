from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..core.models import MarketBar, MarketDataRequest
from ..logging_config import get_logger
from .providers.base import MarketDataProvider

logger = get_logger(__name__)


@dataclass(slots=True)
class MarketDataService:
    provider: MarketDataProvider

    async def fetch_dataframe(self, request: MarketDataRequest) -> pd.DataFrame:
        bars = await self.provider.fetch_ohlcv(request)
        frame = self._to_frame(bars)
        if request.timeframe == "4h":
            frame = self._resample(frame, request.symbol, "4h")
        if len(frame) > request.lookback_bars:
            frame = frame.iloc[-request.lookback_bars :].copy()
        logger.info(
            "market_dataframe_ready",
            symbol=request.symbol,
            timeframe=request.timeframe,
            rows=len(frame),
        )
        return frame

    @staticmethod
    def _to_frame(bars: list[MarketBar]) -> pd.DataFrame:
        frame = pd.DataFrame([bar.model_dump() for bar in bars])
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.set_index("timestamp").sort_index()
        if frame.index.has_duplicates:
            raise ValueError("Market data contains duplicate timestamps.")
        return frame[["symbol", "timeframe", "open", "high", "low", "close", "volume"]]

    @staticmethod
    def _resample(frame: pd.DataFrame, symbol: str, timeframe: str) -> pd.DataFrame:
        aggregated = frame.resample("4h", label="right", closed="right").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        aggregated = aggregated.dropna()
        aggregated["symbol"] = symbol
        aggregated["timeframe"] = timeframe
        return aggregated[["symbol", "timeframe", "open", "high", "low", "close", "volume"]]
