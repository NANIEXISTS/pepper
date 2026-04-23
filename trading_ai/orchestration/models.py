from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

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


class PaperCycleJobCreate(BaseModel):
    symbol: str = Field(min_length=1)
    timeframe: str = Field(default="1h", min_length=2)
    lookback_bars: int = Field(default=600, ge=100, le=5000)
    interval_seconds: int = Field(default=300, ge=60, le=86_400)
    auto_start: bool = True

    @field_validator("timeframe")
    @classmethod
    def normalize_timeframe(cls, value: str) -> str:
        return value.lower()


class PaperCycleJobView(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    symbol: str
    timeframe: str
    lookback_bars: int
    interval_seconds: int
    is_active: bool
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_status: str | None = None
    last_error: str | None = None


class PaperCycleRunView(BaseModel):
    id: int
    job_id: int | None = None
    source: str
    symbol: str
    timeframe: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    execution_status: str | None = None
    trade_executed: bool = False
    error_message: str | None = None
    cycle_payload: dict[str, Any] | None = None
