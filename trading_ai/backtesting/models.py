from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LeakageCheckResult(BaseModel):
    passed: bool
    checked_features: list[str]
    checkpoints_checked: int
    issues: list[str] = Field(default_factory=list)


class EquityPoint(BaseModel):
    timestamp: datetime
    equity: float


class BacktestTrade(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    side: str
    position_fraction: float
    pnl_fraction: float
    bars_held: int = Field(ge=1)


class BacktestMetrics(BaseModel):
    total_return_fraction: float
    annualized_return_fraction: float
    sharpe_ratio: float
    max_drawdown_fraction: float
    win_rate: float = Field(ge=0.0, le=1.0)
    trade_count: int = Field(ge=0)
    exposure_fraction: float = Field(ge=0.0, le=1.0)
    benchmark_return_fraction: float
    warnings: list[str] = Field(default_factory=list)


class BacktestResult(BaseModel):
    strategy_name: str
    symbol: str
    timeframe: str
    started_at: datetime
    ended_at: datetime
    metrics: BacktestMetrics
    equity_curve: list[EquityPoint]
    trades: list[BacktestTrade]


class WalkForwardWindow(BaseModel):
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    result: BacktestResult


class WalkForwardSummary(BaseModel):
    window_count: int = Field(ge=0)
    compounded_return_fraction: float
    average_sharpe_ratio: float
    median_window_return_fraction: float
    worst_window_drawdown_fraction: float
    warnings: list[str] = Field(default_factory=list)


class WalkForwardResult(BaseModel):
    strategy_name: str
    symbol: str
    timeframe: str
    summary: WalkForwardSummary
    windows: list[WalkForwardWindow]
