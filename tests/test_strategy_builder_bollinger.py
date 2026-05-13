from __future__ import annotations

import pytest

from trading_ai.backtesting import BollingerMeanReversionStrategy
from trading_ai.strategy_builder import StrategyCompiler, StrategyGraph, StrategyIndicatorNode, StrategyRiskPolicy, StrategyRuleNode


def test_compiler_drafts_bollinger_graph_from_prompt() -> None:
    compiler = StrategyCompiler()

    draft = compiler.draft_from_prompt(
        "Bollinger 20 mean reversion with 2.5 std bands, exit on revert to mid, with stop loss 2%."
    )

    assert draft.validation.passed is True
    assert draft.graph is not None
    assert draft.graph.family == "bollinger_mean_reversion"
    bollinger = next(indicator for indicator in draft.graph.indicators if indicator.kind == "bollinger")
    assert bollinger.window == 20
    assert bollinger.multiplier == pytest.approx(2.5)
    strategy = compiler.compile_graph(draft.graph)
    assert isinstance(strategy, BollingerMeanReversionStrategy)
    assert strategy.window == 20
    assert strategy.band_multiplier == pytest.approx(2.5)


def test_compiler_keeps_ema_path_for_non_bollinger_prompts() -> None:
    compiler = StrategyCompiler()
    draft = compiler.draft_from_prompt(
        "Buy when EMA 12 crosses above EMA 26 and exit when it crosses below, with stop loss 1.5%."
    )
    assert draft.validation.passed is True
    assert draft.graph is not None
    assert draft.graph.family == "ema_crossover"


def test_apply_parameter_overlay_mutates_known_keys() -> None:
    compiler = StrategyCompiler()
    base = StrategyGraph(
        family="ema_crossover",
        name="EMA baseline",
        indicators=[
            StrategyIndicatorNode(node_id="ema_fast", kind="ema", window=20),
            StrategyIndicatorNode(node_id="ema_slow", kind="ema", window=50),
            StrategyIndicatorNode(node_id="ema_trend", kind="ema", window=200),
        ],
        rules=[
            StrategyRuleNode(
                node_id="entry",
                stage="entry",
                operator="crosses_above",
                left="ema_fast",
                right="ema_slow",
                description="Enter on cross",
            ),
            StrategyRuleNode(
                node_id="exit",
                stage="exit",
                operator="crosses_below",
                left="ema_fast",
                right="ema_slow",
                description="Exit on cross",
            ),
        ],
        risk=StrategyRiskPolicy(stop_loss_percent=0.02),
    )

    mutated = compiler.apply_parameter_overlay(base, {"fast_window": 10, "slow_window": 40})

    assert mutated is not base
    fast = next(indicator for indicator in mutated.indicators if indicator.node_id == "ema_fast")
    slow = next(indicator for indicator in mutated.indicators if indicator.node_id == "ema_slow")
    assert fast.window == 10
    assert slow.window == 40


def test_apply_parameter_overlay_rejects_unknown_keys() -> None:
    compiler = StrategyCompiler()
    base = StrategyGraph(
        family="ema_crossover",
        name="EMA baseline",
        indicators=[
            StrategyIndicatorNode(node_id="ema_fast", kind="ema", window=20),
            StrategyIndicatorNode(node_id="ema_slow", kind="ema", window=50),
        ],
        rules=[
            StrategyRuleNode(
                node_id="entry",
                stage="entry",
                operator="crosses_above",
                left="ema_fast",
                right="ema_slow",
                description="Enter on cross",
            ),
            StrategyRuleNode(
                node_id="exit",
                stage="exit",
                operator="crosses_below",
                left="ema_fast",
                right="ema_slow",
                description="Exit on cross",
            ),
        ],
        risk=StrategyRiskPolicy(stop_loss_percent=0.02),
    )

    with pytest.raises(ValueError, match="Unknown parameters"):
        compiler.apply_parameter_overlay(base, {"unknown_param": 5})


def test_apply_parameter_overlay_revalidates_mutated_values() -> None:
    compiler = StrategyCompiler()
    base = StrategyGraph(
        family="ema_crossover",
        name="EMA baseline",
        indicators=[
            StrategyIndicatorNode(node_id="ema_fast", kind="ema", window=20),
            StrategyIndicatorNode(node_id="ema_slow", kind="ema", window=50),
        ],
        rules=[
            StrategyRuleNode(
                node_id="entry",
                stage="entry",
                operator="crosses_above",
                left="ema_fast",
                right="ema_slow",
                description="Enter on cross",
            ),
            StrategyRuleNode(
                node_id="exit",
                stage="exit",
                operator="crosses_below",
                left="ema_fast",
                right="ema_slow",
                description="Exit on cross",
            ),
        ],
        risk=StrategyRiskPolicy(stop_loss_percent=0.02),
    )

    with pytest.raises(ValueError):
        compiler.apply_parameter_overlay(base, {"fast_window": 1})
