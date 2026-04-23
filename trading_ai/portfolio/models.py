from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class Position(BaseModel):
    symbol: str
    quantity: float = 0.0
    average_entry_price: float = 0.0
    last_price: float = 0.0
    realized_pnl: float = 0.0
    stop_loss_price: float | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price

    @property
    def unrealized_pnl(self) -> float:
        return (self.last_price - self.average_entry_price) * self.quantity


class PortfolioView(BaseModel):
    cash: float
    equity: float
    daily_pnl_fraction: float
    positions: dict[str, Position]
    updated_at: datetime
