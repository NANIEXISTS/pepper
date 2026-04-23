from __future__ import annotations

from enum import StrEnum


class TradingMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    LIMIT = "limit"
    MARKET = "market"


class OrderStatus(StrEnum):
    ACCEPTED = "accepted"
    FILLED = "filled"
    REJECTED = "rejected"
    ERROR = "error"


class TradeSignal(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
