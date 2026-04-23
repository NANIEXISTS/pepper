from __future__ import annotations

import re
from dataclasses import dataclass

from ..backtesting import EmaCrossoverStrategy
from .models import (
    StrategyDraftResult,
    StrategyGraph,
    StrategyIndicatorNode,
    StrategyRiskPolicy,
    StrategyRuleNode,
    StrategyValidationResult,
)

_AMBIGUOUS_TERMS = ("maybe", "roughly", "around", "kind of", "sort of", "ish")
_UNSUPPORTED_TERMS = ("macd", "bollinger", "stochastic", "supertrend", "ichimoku", "vwap")


@dataclass(slots=True)
class StrategyCompiler:
    def draft_from_prompt(self, prompt: str) -> StrategyDraftResult:
        normalized = " ".join(prompt.strip().split())
        lowered = normalized.lower()
        issues: list[str] = []
        warnings: list[str] = []

        ambiguous = [term for term in _AMBIGUOUS_TERMS if term in lowered]
        if ambiguous:
            issues.append("Prompt is ambiguous. Replace vague terms with exact indicator windows and thresholds.")

        unsupported = [term for term in _UNSUPPORTED_TERMS if term in lowered]
        if unsupported:
            issues.append(f"Unsupported indicators referenced: {', '.join(sorted(set(unsupported)))}.")

        ema_windows = self._extract_ema_windows(lowered)
        if len(ema_windows) < 2:
            issues.append("At least two EMA windows are required to compile a crossover strategy.")

        if "cross" not in lowered and "above" not in lowered and "below" not in lowered:
            issues.append("Prompt must describe explicit entry and exit logic, such as EMA cross above and cross below.")

        stop_loss_percent = self._extract_stop_loss_percent(lowered)
        if stop_loss_percent is None:
            issues.append("Missing risk rule: include an explicit stop-loss percentage such as 'stop loss 3%'.")

        if issues:
            return StrategyDraftResult(
                graph=None,
                validation=StrategyValidationResult(
                    passed=False,
                    issues=issues,
                    warnings=warnings,
                    unsupported_terms=sorted(set(unsupported)),
                ),
            )

        unique_windows = sorted(set(ema_windows))
        fast_window = unique_windows[0]
        slow_window = unique_windows[1]
        trend_window = unique_windows[2] if len(unique_windows) >= 3 else 200
        rsi_max = self._extract_rsi_max(lowered)
        long_only = not any(term in lowered for term in ("short", "shorting", "both directions"))

        indicators = [
            StrategyIndicatorNode(node_id="ema_fast", kind="ema", window=fast_window),
            StrategyIndicatorNode(node_id="ema_slow", kind="ema", window=slow_window),
            StrategyIndicatorNode(node_id="ema_trend", kind="ema", window=trend_window),
        ]
        rules = [
            StrategyRuleNode(
                node_id="entry_cross",
                stage="entry",
                operator="crosses_above",
                left="ema_fast",
                right="ema_slow",
                description=f"Enter when EMA {fast_window} crosses above EMA {slow_window}.",
            ),
            StrategyRuleNode(
                node_id="entry_trend",
                stage="filter",
                operator="price_above",
                left="close",
                right="ema_trend",
                description=f"Only take longs when price stays above EMA {trend_window}.",
            ),
            StrategyRuleNode(
                node_id="exit_cross",
                stage="exit",
                operator="crosses_below",
                left="ema_fast",
                right="ema_slow",
                description=f"Exit when EMA {fast_window} crosses below EMA {slow_window}.",
            ),
        ]
        if rsi_max is not None:
            indicators.append(StrategyIndicatorNode(node_id="rsi_entry", kind="rsi", window=14))
            rules.append(
                StrategyRuleNode(
                    node_id="entry_rsi",
                    stage="filter",
                    operator="less_than",
                    left="rsi_entry",
                    right=rsi_max,
                    description=f"Allow entry only when RSI 14 is below {rsi_max:.0f}.",
                )
            )

        graph = StrategyGraph(
            name=f"EMA {fast_window}/{slow_window} crossover",
            source_prompt=normalized,
            indicators=indicators,
            rules=rules,
            risk=StrategyRiskPolicy(
                long_only=long_only,
                stop_loss_percent=stop_loss_percent,
            ),
            metadata={
                "compiler_mode": "deterministic",
                "fast_window": fast_window,
                "slow_window": slow_window,
                "trend_window": trend_window,
            },
        )
        validation = self.validate_graph(graph)
        if not validation.passed:
            return StrategyDraftResult(graph=graph, validation=validation)
        strategy = self.compile_graph(graph)
        return StrategyDraftResult(
            graph=graph,
            validation=validation,
            compiled_strategy_name=strategy.name,
        )

    def validate_graph(self, graph: StrategyGraph) -> StrategyValidationResult:
        issues: list[str] = []
        warnings: list[str] = []
        indicator_ids = {indicator.node_id for indicator in graph.indicators}

        ema_indicators = [indicator for indicator in graph.indicators if indicator.kind == "ema"]
        if len(ema_indicators) < 2:
            issues.append("Strategy graph requires at least two EMA indicators.")

        if graph.risk.stop_loss_percent is None:
            issues.append("Strategy graph is missing stop_loss_percent in the risk policy.")

        for rule in graph.rules:
            if rule.left != "close" and rule.left not in indicator_ids:
                issues.append(f"Rule '{rule.node_id}' references unknown left operand '{rule.left}'.")
            if isinstance(rule.right, str) and rule.right != "close" and rule.right not in indicator_ids:
                issues.append(f"Rule '{rule.node_id}' references unknown right operand '{rule.right}'.")

        if not any(rule.stage == "entry" and rule.operator == "crosses_above" for rule in graph.rules):
            issues.append("Strategy graph requires an entry crossover rule.")
        if not any(rule.stage == "exit" and rule.operator == "crosses_below" for rule in graph.rules):
            issues.append("Strategy graph requires an exit crossover rule.")

        ema_windows = sorted(indicator.window for indicator in ema_indicators)
        if len(ema_windows) >= 2 and ema_windows[0] == ema_windows[1]:
            issues.append("Fast and slow EMA windows must be different.")
        if len(ema_windows) >= 3 and ema_windows[2] <= ema_windows[1]:
            warnings.append("Trend EMA should usually be longer than the slow EMA. Review the graph before trusting it.")

        return StrategyValidationResult(passed=not issues, issues=issues, warnings=warnings)

    def compile_graph(self, graph: StrategyGraph) -> EmaCrossoverStrategy:
        validation = self.validate_graph(graph)
        if not validation.passed:
            raise ValueError("; ".join(validation.issues))

        ema_nodes = sorted((indicator for indicator in graph.indicators if indicator.kind == "ema"), key=lambda item: item.window)
        fast_window = ema_nodes[0].window
        slow_window = ema_nodes[1].window
        trend_window = ema_nodes[2].window if len(ema_nodes) >= 3 else max(200, slow_window)

        rsi_rule = next(
            (
                rule for rule in graph.rules
                if rule.operator == "less_than" and rule.left.startswith("rsi")
            ),
            None,
        )
        entry_rsi_max = float(rsi_rule.right) if rsi_rule and not isinstance(rsi_rule.right, str) else None

        return EmaCrossoverStrategy(
            short_window=fast_window,
            long_window=slow_window,
            trend_filter_window=trend_window,
            long_only=graph.risk.long_only,
            entry_rsi_max=entry_rsi_max,
        )

    @staticmethod
    def _extract_ema_windows(prompt: str) -> list[int]:
        return [int(match.group(1)) for match in re.finditer(r"ema\s*(\d{1,3})", prompt)]

    @staticmethod
    def _extract_stop_loss_percent(prompt: str) -> float | None:
        match = re.search(r"stop(?:-|\s)?loss(?:\s*(?:at|of|=))?\s*(\d+(?:\.\d+)?)\s*%", prompt)
        if match is None:
            return None
        return float(match.group(1)) / 100.0

    @staticmethod
    def _extract_rsi_max(prompt: str) -> float | None:
        match = re.search(r"rsi(?:\s*14)?(?:\s*is)?\s*(?:below|under|<|less than)\s*(\d+(?:\.\d+)?)", prompt)
        if match is None:
            return None
        return float(match.group(1))
