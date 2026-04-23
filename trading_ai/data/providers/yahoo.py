from __future__ import annotations

from datetime import UTC, datetime

import httpx

from ...core.models import MarketBar, MarketDataRequest
from ...logging_config import get_logger
from ...settings import DataSettings
from .base import MarketDataProvider

logger = get_logger(__name__)


class YahooFinanceProvider(MarketDataProvider):
    _INTERVAL_MAP = {
        "5m": "5m",
        "15m": "15m",
        "1h": "60m",
        "4h": "60m",
        "1d": "1d",
    }

    _RANGE_MAP = {
        "5m": "60d",
        "15m": "60d",
        "1h": "730d",
        "4h": "730d",
        "1d": "10y",
    }

    def __init__(self, settings: DataSettings) -> None:
        self.settings = settings

    async def fetch_ohlcv(self, request: MarketDataRequest) -> list[MarketBar]:
        requested_timeframe = request.timeframe
        provider_timeframe = self._provider_timeframe(requested_timeframe)
        params = {
            "interval": provider_timeframe,
            "range": self._RANGE_MAP[requested_timeframe],
            "includePrePost": "false",
            "events": "div,splits",
        }
        url = f"{self.settings.base_url}/v8/finance/chart/{request.symbol}"
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.get(
                url,
                params=params,
                headers={"User-Agent": "TradingAI/0.1"},
            )
            response.raise_for_status()
        payload = response.json()
        result = payload["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        timestamps = result.get("timestamp", [])

        bars: list[MarketBar] = []
        for timestamp, open_, high, low, close, volume in zip(
            timestamps,
            quote.get("open", []),
            quote.get("high", []),
            quote.get("low", []),
            quote.get("close", []),
            quote.get("volume", []),
        ):
            if None in (open_, high, low, close, volume):
                continue
            bars.append(
                MarketBar(
                    symbol=request.symbol,
                    timeframe=provider_timeframe,
                    timestamp=datetime.fromtimestamp(timestamp, tz=UTC),
                    open=float(open_),
                    high=float(high),
                    low=float(low),
                    close=float(close),
                    volume=float(volume),
                )
            )
        if not bars:
            raise ValueError(f"Yahoo returned no OHLCV bars for {request.symbol}.")
        logger.info(
            "market_data_fetched",
            provider="yahoo",
            symbol=request.symbol,
            requested_timeframe=request.timeframe,
            provider_timeframe=provider_timeframe,
            bars=len(bars),
        )
        return bars

    def _provider_timeframe(self, requested_timeframe: str) -> str:
        if requested_timeframe not in self._INTERVAL_MAP:
            raise ValueError(f"Unsupported timeframe: {requested_timeframe}")
        return self._INTERVAL_MAP[requested_timeframe]
