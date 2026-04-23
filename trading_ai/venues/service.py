from __future__ import annotations

from dataclasses import dataclass

from ..settings import TradingSettings
from .models import VenueCapability, VenueCapabilityCatalog

SUPPORTED_TIMEFRAME_MAP: dict[str, str] = {
    "5m": "5Min",
    "15m": "15Min",
    "1h": "1Hour",
    "4h": "4Hour",
    "1d": "1Day",
}
_CRYPTO_QUOTES = {"USD", "USDT", "USDC", "FDUSD", "BUSD", "EUR", "BTC", "ETH"}


def normalize_timeframe_label(timeframe: str) -> str:
    normalized = timeframe.lower()
    if normalized not in SUPPORTED_TIMEFRAME_MAP:
        raise ValueError(f"Unsupported timeframe '{timeframe}'. Supported values: {', '.join(SUPPORTED_TIMEFRAME_MAP)}.")
    return SUPPORTED_TIMEFRAME_MAP[normalized]


def is_probable_crypto_symbol(symbol: str) -> bool:
    normalized = symbol.upper()
    if "/" in normalized:
        return True
    if "-" not in normalized:
        return False
    base, quote = normalized.rsplit("-", maxsplit=1)
    return bool(base) and quote in _CRYPTO_QUOTES


def normalize_alpaca_symbol(symbol: str) -> str:
    normalized = symbol.upper().strip()
    if is_probable_crypto_symbol(normalized):
        return normalized.replace("-", "/")
    return normalized


@dataclass(slots=True)
class VenueCatalogService:
    settings: TradingSettings

    def describe(self) -> VenueCapabilityCatalog:
        routing = [name.lower() for name in self.settings.data.provider_routing]
        live_router = self.settings.execution.live_router.lower()
        return VenueCapabilityCatalog(
            configured_provider=self.settings.data.provider,
            data_routing=routing,
            configured_live_router=live_router,
            venues=[
                VenueCapability(
                    venue_id="ccxt-market-data",
                    venue_kind="market_data",
                    transport="ccxt",
                    configured=self.settings.data.provider == "ccxt" or "ccxt" in routing,
                    supports_market_data=True,
                    supported_timeframes=self.settings.data.supported_timeframes,
                    supports_sandbox=self.settings.exchange.sandbox,
                    symbol_format="BASE/QUOTE with quote fallbacks from config",
                    notes=[
                        "Requires exchange.has['fetchOHLCV'] before data use.",
                        f"Configured exchange: {self.settings.exchange.exchange_id}.",
                    ],
                ),
                VenueCapability(
                    venue_id="alpaca-market-data",
                    venue_kind="market_data",
                    transport="httpx",
                    configured=self.settings.data.provider == "alpaca" or "alpaca" in routing,
                    requires_auth_for_market_data=True,
                    supports_market_data=True,
                    supported_timeframes=self.settings.data.supported_timeframes,
                    symbol_format="Equities use ticker symbols, crypto uses BASE/QUOTE",
                    notes=[
                        "Historical stock bars require Alpaca API credentials.",
                        f"Crypto location configured as {self.settings.alpaca.crypto_location}.",
                        f"Stock feed configured as {self.settings.alpaca.stock_feed}.",
                    ],
                ),
                VenueCapability(
                    venue_id="yahoo-market-data",
                    venue_kind="market_data",
                    transport="httpx",
                    configured=self.settings.data.provider == "yahoo" or "yahoo" in routing,
                    supports_market_data=True,
                    supported_timeframes=self.settings.data.supported_timeframes,
                    symbol_format="Ticker or pair symbols routed through Yahoo Finance history endpoints",
                    notes=[
                        "Fallback-only path. Do not treat as the primary execution-grade venue.",
                    ],
                ),
                VenueCapability(
                    venue_id="ccxt-live-router",
                    venue_kind="broker",
                    transport="ccxt",
                    configured=live_router == "ccxt",
                    supports_order_routing=True,
                    venue_supported_order_types=["market", "limit"],
                    engine_supported_order_types=["market", "limit"],
                    venue_supports_stop_orders=False,
                    engine_exposes_stop_orders=False,
                    supports_sandbox=self.settings.exchange.sandbox,
                    symbol_format="BASE/QUOTE",
                    notes=[
                        "Stop-order support varies by exchange and is not normalized by the current engine.",
                        "Live routing remains disabled until the operational gate passes.",
                    ],
                ),
                VenueCapability(
                    venue_id="alpaca-live-router",
                    venue_kind="broker",
                    transport="httpx",
                    configured=live_router == "alpaca",
                    supports_order_routing=True,
                    venue_supported_order_types=["market", "limit", "stop"],
                    engine_supported_order_types=["market", "limit"],
                    venue_supports_stop_orders=True,
                    engine_exposes_stop_orders=False,
                    supports_sandbox=True,
                    symbol_format="Ticker or BASE/QUOTE",
                    notes=[
                        "Alpaca venue supports stop orders, but the current OrderIntent exposes only market and limit.",
                        "Paper endpoint is available through paper-api.alpaca.markets.",
                    ],
                ),
            ],
        )
