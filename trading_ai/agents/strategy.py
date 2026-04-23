from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..core.enums import TradeSignal
from .models import AgentContext, AnalystOutput, DebateOutput, StrategyOutput


@dataclass(slots=True)
class StrategyAgent:
    async def run(self, ctx: AgentContext, analysis: AnalystOutput, debate: DebateOutput) -> StrategyOutput:
        latest = ctx.features.iloc[-1]
        ema_20 = float(latest["ema_20"])
        ema_50 = float(latest["ema_50"])
        rsi = float(latest["rsi_14"]) if pd.notna(latest["rsi_14"]) else 50.0

        signal = TradeSignal.HOLD
        confidence = min(max((analysis.confidence + abs(debate.consensus_bias)) / 2, 0.0), 1.0)

        if ema_20 > ema_50 and debate.consensus_bias >= 0 and rsi < 72:
            signal = TradeSignal.BUY
        elif ema_20 < ema_50 and debate.consensus_bias < 0:
            signal = TradeSignal.SELL

        rationale = (
            f"Analyst confidence={analysis.confidence:.2f}, debate bias={debate.consensus_bias:.2f}, "
            f"EMA20={ema_20:.2f}, EMA50={ema_50:.2f}, RSI={rsi:.2f}. "
            f"{analysis.summary}"
        )
        return StrategyOutput(
            signal=signal,
            confidence=confidence,
            rationale=rationale,
            metadata={
                "bull_score": debate.bull.score,
                "bear_score": debate.bear.score,
                "debate_bias": debate.consensus_bias,
            },
        )
