from __future__ import annotations

from abc import ABC, abstractmethod

from ...core.models import MarketBar, MarketDataRequest


class MarketDataProvider(ABC):
    @abstractmethod
    async def fetch_ohlcv(self, request: MarketDataRequest) -> list[MarketBar]:
        """Fetch normalized OHLCV bars for a symbol and timeframe."""
