from __future__ import annotations

import pytest

from trading_ai.core.enums import OrderSide
from trading_ai.core.models import OrderIntent
from trading_ai.execution.live_ccxt import CcxtLiveOrderRouter
from trading_ai.settings import ExchangeSettings


@pytest.mark.asyncio
async def test_live_ccxt_router_rejects_when_disabled() -> None:
    router = CcxtLiveOrderRouter(
        settings=ExchangeSettings(exchange_id="binance", sandbox=True),
        enabled=False,
    )
    order = OrderIntent(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        quantity=0.01,
        entry_price=100.0,
        stop_loss_price=95.0,
    )

    with pytest.raises(RuntimeError, match="Live trading is disabled"):
        await router.submit_order(order)
