from __future__ import annotations

from datetime import UTC, datetime

from trading_ai.core.enums import OrderSide, OrderStatus
from trading_ai.core.models import ExecutionReport, OrderIntent
from trading_ai.portfolio import PortfolioService


def test_portfolio_service_applies_fill_and_marks_to_market() -> None:
    portfolio = PortfolioService(starting_cash=10_000)
    order = OrderIntent(
        symbol="BTC-USD",
        side=OrderSide.BUY,
        quantity=1.0,
        entry_price=100.0,
        stop_loss_price=95.0,
    )
    report = ExecutionReport(
        order_id="paper-1",
        status=OrderStatus.FILLED,
        router="paper",
        submitted_at=datetime.now(UTC),
        symbol="BTC-USD",
        side=OrderSide.BUY,
        quantity=1.0,
        message="filled",
        fill_price=100.0,
    )

    portfolio.apply_fill(order, report)
    snapshot = portfolio.snapshot({"BTC-USD": 110.0})

    assert snapshot.cash == 9900.0
    assert snapshot.open_positions == 1
    assert snapshot.equity == 10010.0
