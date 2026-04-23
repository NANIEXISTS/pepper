from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field


class TradeAuditEventView(BaseModel):
    id: int
    created_at: datetime
    agent_name: str
    symbol: str
    signal: str
    confidence: float
    risk_check_passed: bool
    action_taken: str
    rationale: str
    order_payload: dict[str, Any]
    risk_reason: str
    risk_fraction: float | None = None
    router: str
    order_status: str
    report_payload: dict[str, Any]
    metadata_payload: dict[str, Any] = Field(default_factory=dict)


class PortfolioStateView(BaseModel):
    key: str = "paper-default"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    cash: float
    realized_pnl: float = 0.0
    daily_anchor_equity: float
    daily_anchor_date: date
    positions_payload: dict[str, dict[str, Any]] = Field(default_factory=dict)
