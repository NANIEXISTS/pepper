from __future__ import annotations

from ...settings import AlpacaSettings, DataSettings, ExchangeSettings
from .alpaca import AlpacaMarketDataProvider
from .base import MarketDataProvider
from .ccxt import CcxtMarketDataProvider
from .routing import RoutingMarketDataProvider
from .yahoo import YahooFinanceProvider


def build_market_data_provider(
    data_settings: DataSettings,
    exchange_settings: ExchangeSettings,
    alpaca_settings: AlpacaSettings,
) -> MarketDataProvider:
    provider_catalog: dict[str, MarketDataProvider] = {
        "ccxt": CcxtMarketDataProvider(data_settings, exchange_settings),
        "alpaca": AlpacaMarketDataProvider(data_settings, alpaca_settings),
        "yahoo": YahooFinanceProvider(data_settings),
    }
    configured_provider = data_settings.provider.lower()

    if configured_provider in provider_catalog:
        return provider_catalog[configured_provider]
    if configured_provider in {"router", "auto", "hybrid"}:
        ordered_names = [name.lower() for name in data_settings.provider_routing]
        providers = [provider_catalog[name] for name in ordered_names if name in provider_catalog]
        if not providers:
            raise ValueError(
                f"Configured market-data routing order contains no supported providers: {data_settings.provider_routing!r}"
            )
        return RoutingMarketDataProvider(
            providers,
            max_retries=data_settings.provider_max_retries,
            retry_backoff_seconds=data_settings.retry_backoff_seconds,
        )

    raise ValueError(f"Unsupported market-data provider setting: {data_settings.provider}")
