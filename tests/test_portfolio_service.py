from __future__ import annotations

from datetime import UTC, datetime

import pytest

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


def test_portfolio_service_rejects_sell_without_existing_position() -> None:
    portfolio = PortfolioService(starting_cash=10_000)
    order = OrderIntent(
        symbol="BTC-USD",
        side=OrderSide.SELL,
        quantity=1.0,
        entry_price=100.0,
        stop_loss_price=105.0,
    )
    report = ExecutionReport(
        order_id="paper-sell-1",
        status=OrderStatus.FILLED,
        router="paper",
        submitted_at=datetime.now(UTC),
        symbol="BTC-USD",
        side=OrderSide.SELL,
        quantity=1.0,
        message="filled",
        fill_price=99.0,
    )

    with pytest.raises(ValueError, match="without an existing long position"):
        portfolio.apply_fill(order, report)


def test_portfolio_service_removes_closed_losing_position() -> None:
    portfolio = PortfolioService(starting_cash=10_000)
    buy_order = OrderIntent(
        symbol="BTC-USD",
        side=OrderSide.BUY,
        quantity=1.0,
        entry_price=100.0,
        stop_loss_price=95.0,
    )
    buy_report = ExecutionReport(
        order_id="paper-buy-1",
        status=OrderStatus.FILLED,
        router="paper",
        submitted_at=datetime.now(UTC),
        symbol="BTC-USD",
        side=OrderSide.BUY,
        quantity=1.0,
        message="filled",
        fill_price=100.0,
    )
    sell_order = OrderIntent(
        symbol="BTC-USD",
        side=OrderSide.SELL,
        quantity=1.0,
        entry_price=90.0,
        stop_loss_price=95.0,
    )
    sell_report = ExecutionReport(
        order_id="paper-sell-2",
        status=OrderStatus.FILLED,
        router="paper",
        submitted_at=datetime.now(UTC),
        symbol="BTC-USD",
        side=OrderSide.SELL,
        quantity=1.0,
        message="filled",
        fill_price=90.0,
    )

    portfolio.apply_fill(buy_order, buy_report)
    portfolio.apply_fill(sell_order, sell_report)

    assert "BTC-USD" not in portfolio.positions
    assert portfolio.realized_pnl == -10.0


def test_portfolio_snapshot_marks_stale_symbols() -> None:
    portfolio = PortfolioService(starting_cash=10_000)
    order = OrderIntent(
        symbol="BTC-USD",
        side=OrderSide.BUY,
        quantity=1.0,
        entry_price=100.0,
        stop_loss_price=95.0,
    )
    report = ExecutionReport(
        order_id="paper-buy-2",
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
    snapshot = portfolio.snapshot({})

    assert snapshot.stale_symbols == ["BTC-USD"]
