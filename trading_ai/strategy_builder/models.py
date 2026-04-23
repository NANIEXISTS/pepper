from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class StrategyIndicatorNode(BaseModel):
    node_id: str
    kind: Literal["ema", "rsi"]
    window: int = Field(ge=2, le=500)
    source: str = "close"


class StrategyRuleNode(BaseModel):
    node_id: str
    stage: Literal["entry", "exit", "filter"]
    operator: Literal["crosses_above", "crosses_below", "less_than", "greater_than", "price_above", "price_below"]
    left: str
    right: str | float
    description: str


class StrategyRiskPolicy(BaseModel):
    long_only: bool = True
    stop_loss_percent: float | None = Field(default=None, gt=0.0, le=0.5)


class StrategyGraph(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    source_prompt: str | None = None
    indicators: list[StrategyIndicatorNode] = Field(default_factory=list)
    rules: list[StrategyRuleNode] = Field(default_factory=list)
    risk: StrategyRiskPolicy = Field(default_factory=StrategyRiskPolicy)
    metadata: dict[str, str | float | bool] = Field(default_factory=dict)


class StrategyValidationResult(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unsupported_terms: list[str] = Field(default_factory=list)


class StrategyDraftResult(BaseModel):
    compiler_mode: str = "deterministic"
    graph: StrategyGraph | None = None
    validation: StrategyValidationResult
    compiled_strategy_name: str | None = None


class StrategyDraftRequest(BaseModel):
    prompt: str = Field(min_length=12, max_length=3000)


class StrategyValidateRequest(BaseModel):
    graph: StrategyGraph


class StrategyBacktestRequest(BaseModel):
    symbol: str = Field(min_length=1)
    timeframe: str = Field(default="1h", min_length=2)
    lookback_bars: int = Field(default=600, ge=100, le=5000)
    graph: StrategyGraph

    @field_validator("timeframe")
    @classmethod
    def normalize_timeframe(cls, value: str) -> str:
        return value.lower()
