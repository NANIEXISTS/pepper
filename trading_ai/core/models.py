from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, field_validator, model_validator

from .enums import OrderSide, OrderStatus, OrderType, TradeSignal, TradingMode


class MarketDataRequest(BaseModel):
    symbol: str = Field(min_length=1)
    timeframe: str = Field(default="1d", min_length=2)
    lookback_bars: int = Field(default=500, ge=50, le=5000)

    @field_validator("timeframe")
    @classmethod
    def normalize_timeframe(cls, value: str) -> str:
        return value.lower()


class MarketBar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @field_validator("timestamp")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Market bars must use timezone-aware UTC timestamps.")
        return value


class OrderIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    side: OrderSide
    quantity: PositiveFloat
    entry_price: PositiveFloat
    stop_loss_price: PositiveFloat | None = None
    order_type: OrderType = OrderType.LIMIT
    take_profit_price: PositiveFloat | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_price_ladder(self) -> "OrderIntent":
        if self.stop_loss_price is None:
            return self
        if self.side == OrderSide.BUY and self.stop_loss_price >= self.entry_price:
            raise ValueError("Long trades require stop loss below the entry price.")
        if self.side == OrderSide.SELL and self.stop_loss_price <= self.entry_price:
            raise ValueError("Short trades require stop loss above the entry price.")
        return self

    def risk_fraction(self, portfolio_equity: float) -> float:
        if self.stop_loss_price is None:
            return 0.0
        worst_case_loss = abs(self.entry_price - self.stop_loss_price) * self.quantity
        return worst_case_loss / portfolio_equity


class PortfolioSnapshot(BaseModel):
    equity: PositiveFloat
    cash: float = 0.0
    daily_pnl_fraction: float = 0.0
    open_positions: int = Field(default=0, ge=0)


class RiskCheckContext(BaseModel):
    portfolio: PortfolioSnapshot
    order: OrderIntent
    mode: TradingMode = TradingMode.PAPER


class RiskDecision(BaseModel):
    approved: bool
    reason: str
    risk_fraction: float | None = None
    circuit_breaker_triggered: bool = False


class ExecutionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    status: OrderStatus
    router: str
    submitted_at: datetime
    symbol: str
    side: OrderSide
    quantity: float
    message: str
    fill_price: float | None = None


class TradeDecisionLog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str
    symbol: str
    signal: TradeSignal
    confidence: float = Field(ge=0.0, le=1.0)
    risk_check_passed: bool
    action_taken: str
    rationale: str
    metadata: dict[str, Any] = Field(default_factory=dict)
