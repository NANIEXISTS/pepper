from __future__ import annotations

import pytest

from trading_ai.core.enums import OrderSide
from trading_ai.core.models import OrderIntent
from trading_ai.execution.router import PaperOrderRouter


@pytest.mark.asyncio
async def test_paper_router_applies_worse_fill_to_buys_and_sells() -> None:
    router = PaperOrderRouter(fill_slippage_bps=2.0)
    buy_order = OrderIntent(
        symbol="BTC-USD",
        side=OrderSide.BUY,
        quantity=1.0,
        entry_price=100.0,
        stop_loss_price=95.0,
    )
    sell_order = OrderIntent(
        symbol="BTC-USD",
        side=OrderSide.SELL,
        quantity=1.0,
        entry_price=100.0,
        stop_loss_price=105.0,
    )

    buy_report = await router.submit_order(buy_order)
    sell_report = await router.submit_order(sell_order)

    assert buy_report.fill_price is not None
    assert sell_report.fill_price is not None
    assert buy_report.fill_price > buy_order.entry_price
    assert sell_report.fill_price < sell_order.entry_price
