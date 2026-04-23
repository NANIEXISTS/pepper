from __future__ import annotations

from ..settings import TradingSettings
from .live_alpaca import AlpacaLiveOrderRouter
from .live_ccxt import CcxtLiveOrderRouter
from .router import OrderRouter


def build_live_order_router(settings: TradingSettings) -> OrderRouter:
    router_name = settings.execution.live_router.lower()
    if router_name == "ccxt":
        return CcxtLiveOrderRouter(
            settings=settings.exchange,
            enabled=settings.execution.live_trading_enabled,
        )
    if router_name == "alpaca":
        return AlpacaLiveOrderRouter(
            settings=settings.alpaca,
            enabled=settings.execution.live_trading_enabled,
        )
    raise ValueError(f"Unsupported live router setting: {settings.execution.live_router}")
