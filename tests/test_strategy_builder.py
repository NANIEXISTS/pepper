from __future__ import annotations

import pytest

from trading_ai.backtesting import EmaCrossoverStrategy
from trading_ai.strategy_builder import StrategyCompiler


def test_strategy_compiler_builds_valid_graph() -> None:
    compiler = StrategyCompiler()

    draft = compiler.draft_from_prompt(
        "Buy when EMA 20 crosses above EMA 50, only when price is above EMA 200 and RSI 14 is below 70, with stop loss 3%."
    )

    assert draft.validation.passed is True
    assert draft.graph is not None
    assert len(draft.graph.indicators) == 4
    strategy = compiler.compile_graph(draft.graph)
    assert isinstance(strategy, EmaCrossoverStrategy)
    assert strategy.short_window == 20
    assert strategy.long_window == 50
    assert strategy.trend_filter_window == 200
    assert strategy.entry_rsi_max == 70.0


def test_strategy_compiler_blocks_missing_risk_rule() -> None:
    compiler = StrategyCompiler()

    draft = compiler.draft_from_prompt("Buy when EMA 20 crosses above EMA 50 and exit when it crosses below EMA 50.")

    assert draft.validation.passed is False
    assert draft.graph is None
    assert any("stop-loss" in issue.lower() for issue in draft.validation.issues)


def test_strategy_compiler_rejects_invalid_graph_references() -> None:
    compiler = StrategyCompiler()
    draft = compiler.draft_from_prompt(
        "Buy when EMA 20 crosses above EMA 50, only when price is above EMA 200, with stop loss 2%."
    )
    assert draft.graph is not None
    draft.graph.rules[0].right = "ema_missing"

    validation = compiler.validate_graph(draft.graph)

    assert validation.passed is False
    assert any("unknown right operand" in issue.lower() for issue in validation.issues)
