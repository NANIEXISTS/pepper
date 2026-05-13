from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union

from ..backtesting import BollingerMeanReversionStrategy, EmaCrossoverStrategy
from .models import (
    StrategyDraftResult,
    StrategyFamily,
    StrategyGraph,
    StrategyIndicatorNode,
    StrategyRiskPolicy,
    StrategyRuleNode,
    StrategyValidationResult,
)

CompiledStrategy = Union[EmaCrossoverStrategy, BollingerMeanReversionStrategy]

_AMBIGUOUS_TERMS = ("maybe", "roughly", "around", "kind of", "sort of", "ish")
_UNSUPPORTED_TERMS = ("macd", "stochastic", "supertrend", "ichimoku", "vwap")
_MEAN_REVERSION_TERMS = (
    "bollinger",
    "mean reversion",
    "mean-reversion",
    "revert",
    "reversion",
    "band touch",
)


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

        is_mean_reversion = any(term in lowered for term in _MEAN_REVERSION_TERMS)
        stop_loss_percent = self._extract_stop_loss_percent(lowered)
        if stop_loss_percent is None:
            issues.append("Missing risk rule: include an explicit stop-loss percentage such as 'stop loss 3%'.")

        if is_mean_reversion:
            return self._draft_bollinger(
                normalized=normalized,
                lowered=lowered,
                issues=issues,
                warnings=warnings,
                unsupported=unsupported,
                stop_loss_percent=stop_loss_percent,
            )
        return self._draft_ema(
            normalized=normalized,
            lowered=lowered,
            issues=issues,
            warnings=warnings,
            unsupported=unsupported,
            stop_loss_percent=stop_loss_percent,
        )

    def validate_graph(self, graph: StrategyGraph) -> StrategyValidationResult:
        if graph.family == "bollinger_mean_reversion":
            return self._validate_bollinger_graph(graph)
        return self._validate_ema_graph(graph)

    def compile_graph(self, graph: StrategyGraph) -> CompiledStrategy:
        validation = self.validate_graph(graph)
        if not validation.passed:
            raise ValueError("; ".join(validation.issues))
        if graph.family == "bollinger_mean_reversion":
            return self._compile_bollinger(graph)
        return self._compile_ema(graph)

    def apply_parameter_overlay(self, graph: StrategyGraph, parameters: dict[str, float]) -> StrategyGraph:
        """Return a new graph with the supplied parameters mutated in place.

        Used by the optimizer to materialize parameter sweep candidates as
        validated graphs before compiling them. Unknown parameter keys raise so
        the caller is forced to fix the grid rather than silently swallowing
        typos that would all evaluate to the same baseline strategy.
        """

        mutated = graph.model_copy(deep=True)
        recognised = set()
        for indicator in mutated.indicators:
            if indicator.kind == "ema":
                if indicator.node_id == "ema_fast" and "fast_window" in parameters:
                    indicator.window = int(parameters["fast_window"])
                    recognised.add("fast_window")
                if indicator.node_id == "ema_slow" and "slow_window" in parameters:
                    indicator.window = int(parameters["slow_window"])
                    recognised.add("slow_window")
                if indicator.node_id == "ema_trend" and "trend_window" in parameters:
                    indicator.window = int(parameters["trend_window"])
                    recognised.add("trend_window")
            elif indicator.kind == "bollinger":
                if "bollinger_window" in parameters:
                    indicator.window = int(parameters["bollinger_window"])
                    recognised.add("bollinger_window")
                if "band_multiplier" in parameters:
                    indicator.multiplier = float(parameters["band_multiplier"])
                    recognised.add("band_multiplier")
        for rule in mutated.rules:
            if rule.operator == "less_than" and rule.left.startswith("rsi") and "entry_rsi_max" in parameters:
                rule.right = float(parameters["entry_rsi_max"])
                recognised.add("entry_rsi_max")
        unknown = set(parameters) - recognised
        if unknown:
            raise ValueError(f"Unknown parameters for graph: {sorted(unknown)}")
        return StrategyGraph.model_validate(mutated.model_dump())

    def _draft_ema(
        self,
        *,
        normalized: str,
        lowered: str,
        issues: list[str],
        warnings: list[str],
        unsupported: list[str],
        stop_loss_percent: float | None,
    ) -> StrategyDraftResult:
        ema_windows = self._extract_ema_windows(lowered)
        if len(ema_windows) < 2:
            issues.append("At least two EMA windows are required to compile a crossover strategy.")
        if "cross" not in lowered and "above" not in lowered and "below" not in lowered:
            issues.append("Prompt must describe explicit entry and exit logic, such as EMA cross above and cross below.")
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
            family="ema_crossover",
            name=f"EMA {fast_window}/{slow_window} crossover",
            source_prompt=normalized,
            indicators=indicators,
            rules=rules,
            risk=StrategyRiskPolicy(long_only=long_only, stop_loss_percent=stop_loss_percent),
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

    def _draft_bollinger(
        self,
        *,
        normalized: str,
        lowered: str,
        issues: list[str],
        warnings: list[str],
        unsupported: list[str],
        stop_loss_percent: float | None,
    ) -> StrategyDraftResult:
        window = self._extract_bollinger_window(lowered) or 20
        multiplier = self._extract_bollinger_multiplier(lowered) or 2.0
        trend_window = self._extract_trend_window(lowered) or 200
        long_only = not any(term in lowered for term in ("short", "shorting", "both directions"))
        require_bullish_trend = "above ema" in lowered or "above the trend" in lowered
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
        indicators = [
            StrategyIndicatorNode(
                node_id="bb_band",
                kind="bollinger",
                window=window,
                multiplier=multiplier,
            ),
            StrategyIndicatorNode(
                node_id="ema_trend",
                kind="ema",
                window=trend_window,
            ),
        ]
        rules = [
            StrategyRuleNode(
                node_id="entry_band_touch",
                stage="entry",
                operator="price_below",
                left="close",
                right="bb_band",
                description=(
                    f"Enter long when close drops below the lower Bollinger band "
                    f"({window}-period, {multiplier:.1f} std)."
                ),
            ),
            StrategyRuleNode(
                node_id="exit_revert",
                stage="exit",
                operator="reverts_to",
                left="close",
                right="bb_band",
                description="Exit when close reverts back to the rolling mean.",
            ),
        ]
        if require_bullish_trend:
            rules.append(
                StrategyRuleNode(
                    node_id="filter_trend",
                    stage="filter",
                    operator="price_above",
                    left="close",
                    right="ema_trend",
                    description=f"Only take longs while price is above EMA {trend_window}.",
                )
            )

        graph = StrategyGraph(
            family="bollinger_mean_reversion",
            name=f"Bollinger {window}/{multiplier:.1f} mean reversion",
            source_prompt=normalized,
            indicators=indicators,
            rules=rules,
            risk=StrategyRiskPolicy(long_only=long_only, stop_loss_percent=stop_loss_percent),
            metadata={
                "compiler_mode": "deterministic",
                "bollinger_window": window,
                "band_multiplier": multiplier,
                "trend_window": trend_window,
                "require_bullish_trend": require_bullish_trend,
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

    def _validate_ema_graph(self, graph: StrategyGraph) -> StrategyValidationResult:
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

    def _validate_bollinger_graph(self, graph: StrategyGraph) -> StrategyValidationResult:
        issues: list[str] = []
        warnings: list[str] = []
        indicator_ids = {indicator.node_id for indicator in graph.indicators}

        bollinger_indicators = [indicator for indicator in graph.indicators if indicator.kind == "bollinger"]
        if len(bollinger_indicators) != 1:
            issues.append("Bollinger mean-reversion graph requires exactly one bollinger indicator.")
        if graph.risk.stop_loss_percent is None:
            issues.append("Strategy graph is missing stop_loss_percent in the risk policy.")
        for rule in graph.rules:
            if rule.left != "close" and rule.left not in indicator_ids:
                issues.append(f"Rule '{rule.node_id}' references unknown left operand '{rule.left}'.")
            if isinstance(rule.right, str) and rule.right != "close" and rule.right not in indicator_ids:
                issues.append(f"Rule '{rule.node_id}' references unknown right operand '{rule.right}'.")
        if not any(rule.stage == "entry" and rule.operator in ("price_below", "price_above") for rule in graph.rules):
            issues.append("Bollinger graph requires an entry rule with a band-touch operator.")
        if not any(rule.stage == "exit" and rule.operator == "reverts_to" for rule in graph.rules):
            issues.append("Bollinger graph requires a 'reverts_to' exit rule.")
        if bollinger_indicators:
            multiplier = bollinger_indicators[0].multiplier or 0.0
            if multiplier < 1.0:
                warnings.append("Band multiplier under 1 std is unusually tight; expect heavy whipsaw.")
        return StrategyValidationResult(passed=not issues, issues=issues, warnings=warnings)

    def _compile_ema(self, graph: StrategyGraph) -> EmaCrossoverStrategy:
        ema_nodes = sorted(
            (indicator for indicator in graph.indicators if indicator.kind == "ema"),
            key=lambda item: item.window,
        )
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
        entry_rsi_max = (
            float(rsi_rule.right) if rsi_rule and not isinstance(rsi_rule.right, str) else None
        )
        return EmaCrossoverStrategy(
            short_window=fast_window,
            long_window=slow_window,
            trend_filter_window=trend_window,
            long_only=graph.risk.long_only,
            entry_rsi_max=entry_rsi_max,
        )

    def _compile_bollinger(self, graph: StrategyGraph) -> BollingerMeanReversionStrategy:
        bollinger_node = next(indicator for indicator in graph.indicators if indicator.kind == "bollinger")
        ema_node = next(
            (indicator for indicator in graph.indicators if indicator.kind == "ema"),
            None,
        )
        require_bullish = any(
            rule.stage == "filter" and rule.operator == "price_above" and rule.right == (ema_node.node_id if ema_node else "")
            for rule in graph.rules
        )
        return BollingerMeanReversionStrategy(
            window=bollinger_node.window,
            band_multiplier=float(bollinger_node.multiplier or 2.0),
            trend_filter_window=ema_node.window if ema_node else 200,
            long_only=graph.risk.long_only,
            require_bullish_trend=require_bullish,
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

    @staticmethod
    def _extract_bollinger_window(prompt: str) -> int | None:
        match = re.search(r"bollinger(?:\s*\w*)?\s*(\d{1,3})", prompt)
        if match is None:
            return None
        return int(match.group(1))

    @staticmethod
    def _extract_bollinger_multiplier(prompt: str) -> float | None:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:std|standard\s*deviations?|sigma)", prompt)
        if match is None:
            return None
        return float(match.group(1))

    @staticmethod
    def _extract_trend_window(prompt: str) -> int | None:
        match = re.search(r"trend(?:\s*ema)?\s*(\d{1,3})", prompt)
        if match is None:
            return None
        return int(match.group(1))
