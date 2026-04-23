from __future__ import annotations

import pandas as pd
import pytest

from trading_ai.agents import AgentContext, AnalystAgent
from trading_ai.llm import LLMClient
from trading_ai.settings import LlmSettings


@pytest.mark.asyncio
async def test_analyst_agent_handles_zero_close_without_division_error() -> None:
    index = pd.date_range("2025-01-01", periods=1, freq="1h", tz="UTC")
    features = pd.DataFrame(
        {
            "close": [0.0],
            "ema_20": [101.0],
            "ema_50": [100.0],
            "macd": [0.5],
            "rsi_14": [55.0],
        },
        index=index,
    )
    context = AgentContext(
        symbol="BTC-USD",
        timeframe="1h",
        market_frame=features.copy(),
        features=features,
        portfolio_equity=10_000.0,
        available_cash=10_000.0,
        positions={},
    )
    agent = AnalystAgent(llm_client=LLMClient(LlmSettings(provider="disabled")))

    output = await agent.run(context)

    assert output.confidence >= 0.0
    assert output.confidence <= 1.0
    assert output.key_facts["ema_gap"] == 1.0
