from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..llm import LLMClient
from .base import TradingAgent
from .models import AgentContext, AnalystOutput


@dataclass(slots=True)
class AnalystAgent(TradingAgent):
    llm_client: LLMClient

    async def run(self, ctx: AgentContext) -> AnalystOutput:
        latest = ctx.features.iloc[-1]
        close_price = float(latest["close"]) if pd.notna(latest["close"]) else 0.0
        safe_close = close_price if close_price > 0 else 1.0
        ema_gap = float((latest["ema_20"] - latest["ema_50"]) / safe_close)
        macd = float(latest["macd"])
        rsi = float(latest["rsi_14"]) if pd.notna(latest["rsi_14"]) else 50.0
        trend_strength = min(abs(ema_gap) * 100, 1.0)
        confidence = max(min((trend_strength + min(abs(macd) / safe_close, 0.4)), 1.0), 0.0)

        deterministic_summary = (
            f"EMA gap={ema_gap:.4f}, MACD={macd:.4f}, RSI={rsi:.2f}. "
            f"Trend looks {'constructive' if ema_gap > 0 else 'weak'} on the latest bar."
        )
        llm_response = await self.llm_client.generate_text(
            system_prompt="Summarize market context in two concise sentences for a trading desk analyst.",
            user_prompt=deterministic_summary,
        )

        return AnalystOutput(
            summary=f"{deterministic_summary} {llm_response.content}".strip(),
            confidence=confidence,
            key_facts={
                "ema_gap": ema_gap,
                "macd": macd,
                "rsi_14": rsi,
            },
        )
