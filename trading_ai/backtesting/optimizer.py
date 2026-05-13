from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import product
from statistics import median
from typing import Callable, Iterable, Literal, Protocol

import pandas as pd
from pydantic import BaseModel, Field

from ..settings import BacktestingSettings
from .engine import BacktestEngine
from .models import BacktestMetrics


class _Strategy(Protocol):
    name: str

    def generate_target_position(self, frame: pd.DataFrame) -> pd.Series: ...


SelectionMetric = Literal["sharpe_ratio", "total_return_fraction"]


class OptimizationCandidate(BaseModel):
    parameters: dict[str, float]
    in_sample_score: float
    in_sample_metric: SelectionMetric


class OptimizationWindow(BaseModel):
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    candidates_evaluated: int = Field(ge=0)
    selected_parameters: dict[str, float]
    in_sample_score: float
    in_sample_metric: SelectionMetric
    test_metrics: BacktestMetrics


class OptimizationSummary(BaseModel):
    window_count: int = Field(ge=0)
    selection_metric: SelectionMetric
    parameter_grid_size: int = Field(ge=0)
    parameter_combinations_evaluated: int = Field(ge=0)
    out_of_sample_compounded_return_fraction: float
    out_of_sample_average_sharpe_ratio: float
    out_of_sample_median_return_fraction: float
    out_of_sample_worst_drawdown_fraction: float
    parameter_stability: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class OptimizationResult(BaseModel):
    base_strategy_name: str
    symbol: str
    timeframe: str
    summary: OptimizationSummary
    windows: list[OptimizationWindow]
    leaderboard: list[OptimizationCandidate]


@dataclass(slots=True)
class WalkForwardOptimizer:
    """Walk-forward parameter selection.

    For each window the optimizer scores every candidate on the training slice,
    picks the best by the chosen metric, and evaluates that selection on the
    held-out test slice. The reported summary is computed from out-of-sample
    test slices only - no in-sample number is allowed to leak into the headline
    return or Sharpe figures.
    """

    settings: BacktestingSettings
    engine: BacktestEngine

    def optimize(
        self,
        frame: pd.DataFrame,
        *,
        strategy_factory: Callable[[dict[str, float]], _Strategy],
        parameter_grid: dict[str, Iterable[float]],
        symbol: str,
        timeframe: str,
        base_strategy_name: str,
        selection_metric: SelectionMetric = "sharpe_ratio",
        max_combinations: int = 24,
    ) -> OptimizationResult:
        if max_combinations <= 0:
            raise ValueError("max_combinations must be positive.")

        candidates = self._build_candidates(parameter_grid, max_combinations)
        if not candidates:
            raise ValueError("Parameter grid produced no candidates.")

        windows = self._windows(frame)
        if not windows:
            raise ValueError("Not enough bars for walk-forward optimization.")

        warnings: list[str] = []
        if len(windows) <= 1:
            warnings.append("Only one walk-forward window is available; OOS sample is small.")
        if len(candidates) > 64:
            warnings.append("Parameter grid has more than 64 combinations; review for overfitting risk.")

        oos_window_results: list[OptimizationWindow] = []
        leaderboard: list[OptimizationCandidate] = []

        for train_start, train_end, test_start, test_end in windows:
            train_frame = frame.iloc[train_start:train_end].copy()
            full_frame = frame.iloc[train_start:test_end].copy()
            evaluation_start = frame.index[test_start]

            best_score = float("-inf")
            best_params: dict[str, float] | None = None
            evaluated = 0

            for params in candidates:
                try:
                    strategy = strategy_factory(params)
                except (ValueError, TypeError):
                    continue
                try:
                    in_sample_result = self.engine.run(
                        train_frame,
                        strategy=strategy,
                        symbol=symbol,
                        timeframe=timeframe,
                    )
                except (ValueError, ZeroDivisionError):
                    continue
                evaluated += 1
                score = self._score(in_sample_result.metrics, selection_metric)
                if score > best_score:
                    best_score = score
                    best_params = dict(params)
                leaderboard.append(
                    OptimizationCandidate(
                        parameters=dict(params),
                        in_sample_score=float(score),
                        in_sample_metric=selection_metric,
                    )
                )

            if best_params is None:
                continue

            test_strategy = strategy_factory(best_params)
            test_result = self.engine.run(
                full_frame,
                strategy=test_strategy,
                symbol=symbol,
                timeframe=timeframe,
                evaluation_start=evaluation_start,
            )
            oos_window_results.append(
                OptimizationWindow(
                    train_start=frame.index[train_start].to_pydatetime(),
                    train_end=frame.index[train_end - 1].to_pydatetime(),
                    test_start=frame.index[test_start].to_pydatetime(),
                    test_end=frame.index[test_end - 1].to_pydatetime(),
                    candidates_evaluated=evaluated,
                    selected_parameters=dict(best_params),
                    in_sample_score=float(best_score),
                    in_sample_metric=selection_metric,
                    test_metrics=test_result.metrics,
                )
            )

        if not oos_window_results:
            raise ValueError("No walk-forward window produced a usable candidate.")

        leaderboard.sort(key=lambda candidate: candidate.in_sample_score, reverse=True)
        unique_leaderboard: list[OptimizationCandidate] = []
        seen: set[str] = set()
        for candidate in leaderboard:
            key = repr(sorted(candidate.parameters.items()))
            if key in seen:
                continue
            seen.add(key)
            unique_leaderboard.append(candidate)
            if len(unique_leaderboard) >= 10:
                break

        summary = self._summarize(
            windows=oos_window_results,
            selection_metric=selection_metric,
            parameter_grid_size=len(candidates),
            warnings=warnings,
        )

        return OptimizationResult(
            base_strategy_name=base_strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            summary=summary,
            windows=oos_window_results,
            leaderboard=unique_leaderboard,
        )

    def _build_candidates(
        self,
        parameter_grid: dict[str, Iterable[float]],
        max_combinations: int,
    ) -> list[dict[str, float]]:
        keys = list(parameter_grid.keys())
        value_lists = [list(parameter_grid[key]) for key in keys]
        if not keys or any(not values for values in value_lists):
            return []
        full = [dict(zip(keys, combo, strict=True)) for combo in product(*value_lists)]
        if len(full) <= max_combinations:
            return full
        step = max(1, len(full) // max_combinations)
        return full[::step][:max_combinations]

    def _windows(self, frame: pd.DataFrame) -> list[tuple[int, int, int, int]]:
        total = len(frame)
        train = self.settings.train_bars
        test = self.settings.test_bars
        if total < train + test:
            return []
        window_end = total
        windows: list[tuple[int, int, int, int]] = []
        while window_end - (train + test) >= 0 and len(windows) < self.settings.max_walk_forward_windows:
            train_start = window_end - (train + test)
            train_end = train_start + train
            test_start = train_end
            test_end = test_start + test
            windows.append((train_start, train_end, test_start, test_end))
            window_end = train_start + train
        windows.reverse()
        return windows

    def _score(self, metrics: BacktestMetrics, metric: SelectionMetric) -> float:
        return float(getattr(metrics, metric))

    def _summarize(
        self,
        *,
        windows: list[OptimizationWindow],
        selection_metric: SelectionMetric,
        parameter_grid_size: int,
        warnings: list[str],
    ) -> OptimizationSummary:
        compounded = 1.0
        sharpe_values: list[float] = []
        returns: list[float] = []
        drawdowns: list[float] = []
        param_observations: dict[str, list[float]] = {}
        emitted_warnings = list(warnings)

        for window in windows:
            compounded *= 1 + window.test_metrics.total_return_fraction
            sharpe_values.append(window.test_metrics.sharpe_ratio)
            returns.append(window.test_metrics.total_return_fraction)
            drawdowns.append(window.test_metrics.max_drawdown_fraction)
            for warning in window.test_metrics.warnings:
                if warning not in emitted_warnings:
                    emitted_warnings.append(warning)
            for key, value in window.selected_parameters.items():
                param_observations.setdefault(key, []).append(float(value))

        stability: dict[str, float] = {}
        for key, observations in param_observations.items():
            if len(observations) < 2:
                stability[key] = 1.0
                continue
            mean = sum(observations) / len(observations)
            if mean == 0:
                stability[key] = 1.0 if all(value == 0 for value in observations) else 0.0
                continue
            variance = sum((value - mean) ** 2 for value in observations) / len(observations)
            cv = (variance ** 0.5) / abs(mean)
            stability[key] = max(0.0, 1.0 - min(cv, 1.0))

        evaluated_total = sum(window.candidates_evaluated for window in windows)
        return OptimizationSummary(
            window_count=len(windows),
            selection_metric=selection_metric,
            parameter_grid_size=parameter_grid_size,
            parameter_combinations_evaluated=evaluated_total,
            out_of_sample_compounded_return_fraction=compounded - 1,
            out_of_sample_average_sharpe_ratio=(sum(sharpe_values) / len(sharpe_values)),
            out_of_sample_median_return_fraction=median(returns),
            out_of_sample_worst_drawdown_fraction=min(drawdowns),
            parameter_stability=stability,
            warnings=emitted_warnings,
        )
