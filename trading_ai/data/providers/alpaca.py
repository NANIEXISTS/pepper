from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from ...core.models import MarketBar, MarketDataRequest
from ...logging_config import get_logger
from ...settings import AlpacaSettings, DataSettings
from ...venues import is_probable_crypto_symbol, normalize_alpaca_symbol, normalize_timeframe_label
from .base import MarketDataProvider

logger = get_logger(__name__)


@dataclass(slots=True)
class AlpacaMarketDataProvider(MarketDataProvider):
    data_settings: DataSettings
    alpaca_settings: AlpacaSettings
    name: str = "alpaca"

    async def fetch_ohlcv(self, request: MarketDataRequest) -> list[MarketBar]:
        asset_kind = "crypto" if is_probable_crypto_symbol(request.symbol) else "stock"
        provider_symbol = normalize_alpaca_symbol(request.symbol)
        provider_timeframe = normalize_timeframe_label(request.timeframe)
        end = datetime.now(UTC).replace(microsecond=0)
        start = end - self._lookback_span(request.timeframe, request.lookback_bars)

        if asset_kind == "stock" and (not self.alpaca_settings.api_key or not self.alpaca_settings.api_secret):
            raise RuntimeError("Alpaca stock market data requires APCA credentials in local config or .env.")

        if asset_kind == "crypto":
            url = (
                f"{self.alpaca_settings.data_base_url.rstrip('/')}/v1beta3/crypto/"
                f"{self.alpaca_settings.crypto_location}/bars"
            )
            params = {
                "symbols": provider_symbol,
                "timeframe": provider_timeframe,
                "start": start.isoformat().replace("+00:00", "Z"),
                "end": end.isoformat().replace("+00:00", "Z"),
                "limit": request.lookback_bars,
            }
        else:
            url = f"{self.alpaca_settings.data_base_url.rstrip('/')}/v2/stocks/bars"
            params = {
                "symbols": provider_symbol,
                "timeframe": provider_timeframe,
                "start": start.isoformat().replace("+00:00", "Z"),
                "end": end.isoformat().replace("+00:00", "Z"),
                "limit": request.lookback_bars,
                "feed": self.alpaca_settings.stock_feed,
                "adjustment": "raw",
            }

        async with httpx.AsyncClient(timeout=self.data_settings.request_timeout_seconds) as client:
            response = await client.get(url, params=params, headers=self._headers(asset_kind))
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text.strip() or str(exc)
                raise RuntimeError(
                    f"Alpaca {asset_kind} bars request failed with {exc.response.status_code}: {detail}"
                ) from exc
            payload = response.json()

        rows = self._extract_rows(payload, provider_symbol)
        bars: list[MarketBar] = []
        for row in rows:
            timestamp = row.get("t") or row.get("timestamp")
            open_ = row.get("o") if "o" in row else row.get("open")
            high = row.get("h") if "h" in row else row.get("high")
            low = row.get("l") if "l" in row else row.get("low")
            close = row.get("c") if "c" in row else row.get("close")
            volume = row.get("v") if "v" in row else row.get("volume")
            if None in (timestamp, open_, high, low, close, volume):
                continue
            bars.append(
                MarketBar(
                    symbol=request.symbol,
                    timeframe=request.timeframe,
                    timestamp=self._parse_timestamp(timestamp),
                    open=float(open_),
                    high=float(high),
                    low=float(low),
                    close=float(close),
                    volume=float(volume),
                )
            )

        if not bars:
            raise RuntimeError(f"Alpaca returned no OHLCV bars for {request.symbol}.")

        logger.info(
            "market_data_fetched",
            provider=self.name,
            symbol=request.symbol,
            provider_symbol=provider_symbol,
            requested_timeframe=request.timeframe,
            provider_timeframe=provider_timeframe,
            bars=len(bars),
            asset_kind=asset_kind,
        )
        return bars[-request.lookback_bars :]

    def _headers(self, asset_kind: str) -> dict[str, str]:
        if asset_kind == "crypto" and (not self.alpaca_settings.api_key or not self.alpaca_settings.api_secret):
            return {}
        return {
            "APCA-API-KEY-ID": self.alpaca_settings.api_key or "",
            "APCA-API-SECRET-KEY": self.alpaca_settings.api_secret or "",
        }

    @staticmethod
    def _extract_rows(payload: dict, provider_symbol: str) -> list[dict]:
        bars = payload.get("bars")
        if isinstance(bars, list):
            return bars
        if not isinstance(bars, dict) or not bars:
            raise RuntimeError("Alpaca response does not contain a bars payload.")
        if provider_symbol in bars:
            rows = bars[provider_symbol]
            if isinstance(rows, list):
                return rows
        first_rows = next(iter(bars.values()))
        if isinstance(first_rows, list):
            return first_rows
        raise RuntimeError("Alpaca bars payload is malformed.")

    @staticmethod
    def _parse_timestamp(value: str | datetime) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(UTC)
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)

    @staticmethod
    def _lookback_span(timeframe: str, lookback_bars: int) -> timedelta:
        mapping = {
            "5m": timedelta(minutes=5),
            "15m": timedelta(minutes=15),
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
            "1d": timedelta(days=1),
        }
        step = mapping.get(timeframe.lower())
        if step is None:
            raise ValueError(f"Unsupported timeframe for Alpaca provider: {timeframe}")
        return step * max(lookback_bars + 4, 8)
