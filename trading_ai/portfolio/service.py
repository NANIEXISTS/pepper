from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from ..core.models import ExecutionReport, OrderIntent, PortfolioSnapshot
from ..logging_config import get_logger
from .models import PortfolioView, Position

logger = get_logger(__name__)


@dataclass(slots=True)
class PortfolioService:
    starting_cash: float
    cash: float = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0
    daily_anchor_equity: float = field(init=False)
    daily_anchor_date: date = field(init=False)

    def __post_init__(self) -> None:
        self.cash = self.starting_cash
        self.daily_anchor_equity = self.starting_cash
        self.daily_anchor_date = datetime.now(UTC).date()

    def mark_to_market(self, prices: dict[str, float]) -> PortfolioView:
        now = datetime.now(UTC)
        self._reset_daily_anchor_if_needed(now, prices)
        stale_symbols: list[str] = []

        for symbol, position in self.positions.items():
            if symbol in prices:
                position.last_price = prices[symbol]
                position.updated_at = now
            elif abs(position.quantity) > 1e-12:
                stale_symbols.append(symbol)

        if stale_symbols:
            logger.warning("portfolio_prices_stale", stale_symbols=stale_symbols)

        equity = self.cash + sum(position.market_value for position in self.positions.values())
        daily_pnl_fraction = ((equity / self.daily_anchor_equity) - 1.0) if self.daily_anchor_equity else 0.0
        return PortfolioView(
            cash=self.cash,
            equity=equity,
            daily_pnl_fraction=daily_pnl_fraction,
            positions={symbol: position for symbol, position in self.positions.items() if abs(position.quantity) > 1e-12},
            stale_symbols=stale_symbols,
            updated_at=now,
        )

    def snapshot(self, prices: dict[str, float]) -> PortfolioSnapshot:
        view = self.mark_to_market(prices)
        return PortfolioSnapshot(
            equity=max(view.equity, 0.01),
            cash=view.cash,
            daily_pnl_fraction=view.daily_pnl_fraction,
            open_positions=len(view.positions),
            stale_symbols=view.stale_symbols,
        )

    def apply_fill(self, order: OrderIntent, report: ExecutionReport) -> None:
        if report.fill_price is None:
            return

        fill_price = report.fill_price
        quantity = order.quantity if order.side.value == "buy" else -order.quantity
        position = self.positions.get(order.symbol, Position(symbol=order.symbol))

        if quantity > 0:
            total_cost = fill_price * quantity
            self.cash -= total_cost
            new_quantity = position.quantity + quantity
            if new_quantity <= 0:
                position.quantity = 0.0
                position.average_entry_price = 0.0
            else:
                weighted_cost = (position.quantity * position.average_entry_price) + total_cost
                position.quantity = new_quantity
                position.average_entry_price = weighted_cost / new_quantity
        else:
            if position.quantity <= 0:
                raise ValueError(f"Cannot sell {order.symbol} without an existing long position.")
            sell_quantity = abs(quantity)
            if sell_quantity - position.quantity > 1e-12:
                raise ValueError(
                    f"Cannot sell {sell_quantity} units of {order.symbol}; only {position.quantity} units are held."
                )
            realized = (fill_price - position.average_entry_price) * sell_quantity
            self.cash += fill_price * sell_quantity
            self.realized_pnl += realized
            position.realized_pnl += realized
            position.quantity = max(position.quantity - sell_quantity, 0.0)
            if position.quantity == 0.0:
                position.average_entry_price = 0.0
                position.stop_loss_price = None

        position.last_price = fill_price
        position.stop_loss_price = order.stop_loss_price
        position.updated_at = datetime.now(UTC)

        if position.quantity == 0.0:
            self.positions.pop(order.symbol, None)
        else:
            self.positions[order.symbol] = position

    def _reset_daily_anchor_if_needed(self, now: datetime, prices: dict[str, float]) -> None:
        if now.date() == self.daily_anchor_date:
            return
        for symbol, position in self.positions.items():
            if symbol in prices:
                position.last_price = prices[symbol]
        self.daily_anchor_equity = self.cash + sum(position.market_value for position in self.positions.values())
        self.daily_anchor_date = now.date()
