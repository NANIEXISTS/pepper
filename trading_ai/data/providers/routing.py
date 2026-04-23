from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ...core.models import MarketBar, MarketDataRequest
from ..exceptions import MarketDataUnavailableError
from ...logging_config import get_logger
from .base import MarketDataProvider

logger = get_logger(__name__)


@dataclass(slots=True)
class RoutingMarketDataProvider(MarketDataProvider):
    providers: list[MarketDataProvider]
    name: str = "router"
    max_retries: int = 1
    retry_backoff_seconds: float = 0.5

    async def fetch_ohlcv(self, request: MarketDataRequest) -> list[MarketBar]:
        if not self.providers:
            raise MarketDataUnavailableError(
                symbol=request.symbol,
                timeframe=request.timeframe,
                failures=["Market data routing requires at least one provider."],
            )

        failures: list[str] = []
        for provider in self.providers:
            provider_name = getattr(provider, "name", provider.__class__.__name__)
            for attempt in range(self.max_retries + 1):
                try:
                    return await provider.fetch_ohlcv(request)
                except Exception as exc:
                    failures.append(f"{provider_name} attempt {attempt + 1}: {exc}")
                    logger.warning(
                        "market_data_provider_failed",
                        provider=provider_name,
                        symbol=request.symbol,
                        timeframe=request.timeframe,
                        attempt=attempt + 1,
                        error=str(exc),
                    )
                    if attempt < self.max_retries and self.retry_backoff_seconds > 0:
                        await asyncio.sleep(self.retry_backoff_seconds * (attempt + 1))

        raise MarketDataUnavailableError(
            symbol=request.symbol,
            timeframe=request.timeframe,
            failures=failures,
        )
