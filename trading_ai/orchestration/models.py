from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from ..agents.models import AnalystOutput, DebateOutput, StrategyOutput
from ..alerts import AlertRecord
from ..core.models import ExecutionReport
from ..portfolio.models import PortfolioView


class PaperTradingCycleResult(BaseModel):
    symbol: str
    timeframe: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    latest_price: float
    portfolio: PortfolioView
    analysis: AnalystOutput
    debate: DebateOutput
    strategy: StrategyOutput
    execution_report: ExecutionReport | None = None
    alert: AlertRecord | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
