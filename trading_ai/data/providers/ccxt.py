from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import ccxt.async_support as ccxt_async

from ...core.models import MarketBar, MarketDataRequest
from ...logging_config import get_logger
from ...settings import DataSettings, ExchangeSettings
from .base import MarketDataProvider

logger = get_logger(__name__)


@dataclass(slots=True)
class CcxtMarketDataProvider(MarketDataProvider):
    data_settings: DataSettings
    exchange_settings: ExchangeSettings
    name: str = "ccxt"

    async def fetch_ohlcv(self, request: MarketDataRequest) -> list[MarketBar]:
        exchange_class = getattr(ccxt_async, self.exchange_settings.exchange_id, None)
        if exchange_class is None:
            raise RuntimeError(f"Unsupported ccxt exchange: {self.exchange_settings.exchange_id}")

        exchange = exchange_class({"enableRateLimit": True})
        try:
            await exchange.load_markets()
            if not bool(exchange.has.get("fetchOHLCV")):
                raise RuntimeError(
                    f"Exchange capability check failed: {self.exchange_settings.exchange_id} does not report fetchOHLCV support."
                )

            provider_timeframe = self._provider_timeframe(exchange, request.timeframe)
            resolved_symbol = self._resolve_symbol(exchange, request.symbol)
            limit = max(request.lookback_bars, 50)
            timeframe_seconds = int(exchange.parse_timeframe(provider_timeframe))
            since = exchange.milliseconds() - (timeframe_seconds * 1000 * limit)
            rows = await exchange.fetch_ohlcv(
                resolved_symbol,
                timeframe=provider_timeframe,
                since=since,
                limit=limit,
            )

            bars: list[MarketBar] = []
            for row in rows:
                if len(row) < 6:
                    raise ValueError(f"ccxt returned malformed OHLCV row for {resolved_symbol}: {row!r}")
                timestamp, open_, high, low, close, volume = row[:6]
                if None in (timestamp, open_, high, low, close, volume):
                    continue
                bars.append(
                    MarketBar(
                        symbol=request.symbol,
                        timeframe=provider_timeframe,
                        timestamp=datetime.fromtimestamp(int(timestamp) / 1000, tz=UTC),
                        open=float(open_),
                        high=float(high),
                        low=float(low),
                        close=float(close),
                        volume=float(volume),
                    )
                )
            if not bars:
                raise ValueError(f"ccxt returned no OHLCV bars for {request.symbol}.")

            logger.info(
                "market_data_fetched",
                provider=self.name,
                exchange_id=self.exchange_settings.exchange_id,
                symbol=request.symbol,
                provider_symbol=resolved_symbol,
                requested_timeframe=request.timeframe,
                provider_timeframe=provider_timeframe,
                bars=len(bars),
            )
            return bars[-request.lookback_bars :]
        finally:
            await exchange.close()

    @staticmethod
    def _provider_timeframe(exchange, requested_timeframe: str) -> str:  # noqa: ANN001
        supported_timeframes = exchange.timeframes or {}
        if supported_timeframes and requested_timeframe not in supported_timeframes:
            raise RuntimeError(
                f"Exchange {exchange.id} does not advertise OHLCV support for timeframe {requested_timeframe}."
            )
        return requested_timeframe

    def _resolve_symbol(self, exchange, symbol: str) -> str:  # noqa: ANN001
        normalized = symbol.upper()
        if normalized in exchange.symbols:
            return normalized

        slash_symbol = normalized.replace("-", "/")
        if slash_symbol in exchange.symbols:
            return slash_symbol

        if "/" in slash_symbol:
            base, quote = slash_symbol.split("/", maxsplit=1)
        elif "-" in normalized:
            base, quote = normalized.split("-", maxsplit=1)
        else:
            raise RuntimeError(f"Unable to normalize market-data symbol for ccxt: {symbol}")

        candidates = [f"{base}/{quote}"]
        if quote == "USD":
            candidates.extend(f"{base}/{fallback}" for fallback in self.data_settings.ccxt_quote_fallbacks)

        for candidate in candidates:
            if candidate in exchange.symbols:
                if candidate != symbol:
                    logger.warning(
                        "market_symbol_remapped",
                        provider=self.name,
                        requested_symbol=symbol,
                        resolved_symbol=candidate,
                        exchange_id=self.exchange_settings.exchange_id,
                    )
                return candidate

        raise RuntimeError(
            f"Exchange {exchange.id} has no supported market for requested symbol {symbol}. Tried: {', '.join(candidates)}"
        )
