from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from ..core.enums import TradeSignal
from ..portfolio.models import Position


@dataclass(slots=True)
class AgentContext:
    symbol: str
    timeframe: str
    market_frame: pd.DataFrame
    features: pd.DataFrame
    portfolio_equity: float
    available_cash: float
    positions: dict[str, Position]
    metadata: dict[str, Any] = field(default_factory=dict)


class AnalystOutput(BaseModel):
    agent_name: str = "analyst-agent"
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    key_facts: dict[str, float] = Field(default_factory=dict)


class DebateArgument(BaseModel):
    agent_name: str
    stance: str
    score: float = Field(ge=0.0, le=1.0)
    argument: str


class DebateOutput(BaseModel):
    bull: DebateArgument
    bear: DebateArgument
    consensus_bias: float = Field(ge=-1.0, le=1.0)


class StrategyOutput(BaseModel):
    agent_name: str = "strategy-agent"
    signal: TradeSignal
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    metadata: dict[str, Any] = Field(default_factory=dict)
