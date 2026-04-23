from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .models import AgentContext, AnalystOutput, DebateArgument, DebateOutput


@dataclass(slots=True)
class BullAgent:
    async def run(self, ctx: AgentContext, analysis: AnalystOutput) -> DebateArgument:
        latest = ctx.features.iloc[-1]
        score = 0.5
        reasons: list[str] = []
        if latest["ema_20"] > latest["ema_50"]:
            score += 0.2
            reasons.append("fast EMA is above slow EMA")
        if latest["macd"] > latest["macd_signal"]:
            score += 0.15
            reasons.append("MACD is above the signal line")
        if pd.notna(latest["rsi_14"]) and latest["rsi_14"] < 70:
            score += 0.1
            reasons.append("RSI is not overbought yet")
        return DebateArgument(
            agent_name="bull-agent",
            stance="bull",
            score=min(score, 1.0),
            argument="Bull case: " + (", ".join(reasons) if reasons else analysis.summary),
        )


@dataclass(slots=True)
class BearAgent:
    async def run(self, ctx: AgentContext, analysis: AnalystOutput) -> DebateArgument:
        latest = ctx.features.iloc[-1]
        score = 0.5
        reasons: list[str] = []
        if latest["ema_20"] < latest["ema_50"]:
            score += 0.2
            reasons.append("fast EMA is below slow EMA")
        if latest["macd"] < latest["macd_signal"]:
            score += 0.15
            reasons.append("MACD is below the signal line")
        if pd.notna(latest["rsi_14"]) and latest["rsi_14"] > 30:
            score += 0.1
            reasons.append("RSI still has room to fall")
        return DebateArgument(
            agent_name="bear-agent",
            stance="bear",
            score=min(score, 1.0),
            argument="Bear case: " + (", ".join(reasons) if reasons else analysis.summary),
        )


@dataclass(slots=True)
class DebateLayer:
    bull_agent: BullAgent
    bear_agent: BearAgent

    async def run(self, ctx: AgentContext, analysis: AnalystOutput) -> DebateOutput:
        bull = await self.bull_agent.run(ctx, analysis)
        bear = await self.bear_agent.run(ctx, analysis)
        bias = max(min(bull.score - bear.score, 1.0), -1.0)
        return DebateOutput(
            bull=bull,
            bear=bear,
            consensus_bias=bias,
        )
