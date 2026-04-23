from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import math

import pandas as pd

from ..core.models import MarketBar, MarketDataRequest
from ..logging_config import get_logger
from .exceptions import MarketDataUnavailableError
from .providers.base import MarketDataProvider

logger = get_logger(__name__)


@dataclass(slots=True)
class CachedMarketFrame:
    frame: pd.DataFrame
    cached_at: datetime


@dataclass(slots=True)
class MarketDataService:
    provider: MarketDataProvider
    cache_max_staleness_seconds: int = 900
    _cache: dict[str, CachedMarketFrame] = field(default_factory=dict)

    async def fetch_dataframe(self, request: MarketDataRequest) -> pd.DataFrame:
        cache_key = self._cache_key(request)
        try:
            bars = await self.provider.fetch_ohlcv(request)
            frame = self._prepare_frame(bars, request)
            cached_frame = frame.copy(deep=True)
            cached_frame.attrs = dict(frame.attrs)
            self._cache[cache_key] = CachedMarketFrame(frame=cached_frame, cached_at=datetime.now(UTC))
            return frame
        except Exception as exc:
            return self._frame_from_cache(cache_key, request, exc)

    @staticmethod
    def _to_frame(bars: list[MarketBar]) -> pd.DataFrame:
        if not bars:
            raise ValueError("Market data provider returned no bars.")
        frame = pd.DataFrame([bar.model_dump() for bar in bars])
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.set_index("timestamp").sort_index()
        if frame.index.has_duplicates:
            raise ValueError("Market data contains duplicate timestamps.")
        return frame[["symbol", "timeframe", "open", "high", "low", "close", "volume"]]

    def _prepare_frame(self, bars: list[MarketBar], request: MarketDataRequest) -> pd.DataFrame:
        frame = self._to_frame(bars)
        provider_timeframe = str(frame["timeframe"].iloc[-1])
        self._validate_frame(frame, provider_timeframe)
        if provider_timeframe != request.timeframe:
            frame = self._resample(frame, request.symbol, provider_timeframe, request.timeframe)
        if len(frame) > request.lookback_bars:
            frame = frame.iloc[-request.lookback_bars :].copy()
        self._validate_frame(frame, request.timeframe)
        frame.attrs["provider"] = getattr(self.provider, "name", self.provider.__class__.__name__)
        frame.attrs["source_timeframe"] = provider_timeframe
        frame.attrs["stale"] = False
        frame.attrs["cache_age_seconds"] = 0.0
        frame.attrs["provider_failures"] = []
        frame.attrs["fresh_as_of"] = datetime.now(UTC).isoformat()
        logger.info(
            "market_dataframe_ready",
            symbol=request.symbol,
            timeframe=request.timeframe,
            source_timeframe=provider_timeframe,
            rows=len(frame),
            stale=False,
        )
        return frame

    def _frame_from_cache(self, cache_key: str, request: MarketDataRequest, exc: Exception) -> pd.DataFrame:
        failures = self._failure_details(exc)
        cached = self._cache.get(cache_key)
        if cached is None:
            raise self._unavailable_error(request, failures, cached_available=False) from exc

        age_seconds = (datetime.now(UTC) - cached.cached_at).total_seconds()
        if age_seconds > self.cache_max_staleness_seconds:
            raise self._unavailable_error(
                request,
                failures,
                cached_available=True,
                cache_age_seconds=age_seconds,
            ) from exc

        frame = cached.frame.copy(deep=True)
        frame.attrs = dict(cached.frame.attrs)
        if len(frame) > request.lookback_bars:
            frame = frame.iloc[-request.lookback_bars :].copy()
            frame.attrs = dict(cached.frame.attrs)
        frame.attrs["stale"] = True
        frame.attrs["cache_age_seconds"] = age_seconds
        frame.attrs["provider_failures"] = failures
        frame.attrs["fresh_as_of"] = cached.cached_at.isoformat()
        logger.warning(
            "market_dataframe_cache_used",
            symbol=request.symbol,
            timeframe=request.timeframe,
            cache_age_seconds=age_seconds,
            failures=failures,
            rows=len(frame),
        )
        return frame

    @staticmethod
    def _failure_details(exc: Exception) -> list[str]:
        if isinstance(exc, MarketDataUnavailableError):
            return exc.failures or [str(exc)]
        return [str(exc)]

    def _unavailable_error(
        self,
        request: MarketDataRequest,
        failures: list[str],
        *,
        cached_available: bool,
        cache_age_seconds: float | None = None,
    ) -> MarketDataUnavailableError:
        return MarketDataUnavailableError(
            symbol=request.symbol,
            timeframe=request.timeframe,
            failures=failures,
            cached_available=cached_available,
            cache_age_seconds=cache_age_seconds,
        )

    @staticmethod
    def _cache_key(request: MarketDataRequest) -> str:
        return f"{request.symbol.upper()}::{request.timeframe.lower()}"

    @staticmethod
    def _resample(frame: pd.DataFrame, symbol: str, source_timeframe: str, target_timeframe: str) -> pd.DataFrame:
        if source_timeframe != "1h" or target_timeframe != "4h":
            raise ValueError(
                f"Unsupported market-data resample path: {source_timeframe} -> {target_timeframe}."
            )
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
        aggregated["timeframe"] = target_timeframe
        return aggregated[["symbol", "timeframe", "open", "high", "low", "close", "volume"]]

    @staticmethod
    def _validate_frame(frame: pd.DataFrame, timeframe: str) -> None:
        if frame.empty:
            raise ValueError("Market data frame is empty.")

        numeric_columns = ["open", "high", "low", "close", "volume"]
        if frame[numeric_columns].isna().any().any():
            raise ValueError("Market data contains null OHLCV values.")
        if not frame[numeric_columns].stack().map(math.isfinite).all():
            raise ValueError("Market data contains non-finite OHLCV values.")
        if (frame["volume"] < 0).any():
            raise ValueError("Market data contains negative volume.")

        highest_valid = frame[["open", "close", "low"]].max(axis=1)
        lowest_valid = frame[["open", "close", "high"]].min(axis=1)
        if (frame["high"] < highest_valid).any():
            raise ValueError("Market data contains candles with highs below traded prices.")
        if (frame["low"] > lowest_valid).any():
            raise ValueError("Market data contains candles with lows above traded prices.")

        gap_count = MarketDataService._gap_count(frame.index, timeframe)
        frame.attrs["gap_count"] = gap_count
        if gap_count > 0:
            logger.warning(
                "market_data_gaps_detected",
                timeframe=timeframe,
                gap_count=gap_count,
                first_timestamp=frame.index[0].isoformat(),
                last_timestamp=frame.index[-1].isoformat(),
            )

    @staticmethod
    def _gap_count(index: pd.DatetimeIndex, timeframe: str) -> int:
        expected_delta = MarketDataService._expected_delta(timeframe)
        if expected_delta is None or len(index) < 2:
            return 0
        gaps = index.to_series().diff().dropna()
        return int((gaps > expected_delta * 1.5).sum())

    @staticmethod
    def _expected_delta(timeframe: str) -> timedelta | None:
        mapping = {
            "5m": timedelta(minutes=5),
            "15m": timedelta(minutes=15),
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
        }
        return mapping.get(timeframe)
