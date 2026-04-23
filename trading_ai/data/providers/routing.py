from __future__ import annotations

from dataclasses import dataclass

from ...core.models import MarketBar, MarketDataRequest
from ...logging_config import get_logger
from .base import MarketDataProvider

logger = get_logger(__name__)


@dataclass(slots=True)
class RoutingMarketDataProvider(MarketDataProvider):
    providers: list[MarketDataProvider]
    name: str = "router"

    async def fetch_ohlcv(self, request: MarketDataRequest) -> list[MarketBar]:
        if not self.providers:
            raise RuntimeError("Market data routing requires at least one provider.")

        failures: list[str] = []
        for provider in self.providers:
            try:
                return await provider.fetch_ohlcv(request)
            except Exception as exc:
                failures.append(f"{getattr(provider, 'name', provider.__class__.__name__)}: {exc}")
                logger.warning(
                    "market_data_provider_failed",
                    provider=getattr(provider, "name", provider.__class__.__name__),
                    symbol=request.symbol,
                    timeframe=request.timeframe,
                    error=str(exc),
                )

        raise RuntimeError(
            f"All market-data providers failed for {request.symbol} {request.timeframe}. "
            f"Failures: {' | '.join(failures)}"
        )
