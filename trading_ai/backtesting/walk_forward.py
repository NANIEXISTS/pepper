from __future__ import annotations

from dataclasses import dataclass
from statistics import median

import pandas as pd

from ..settings import BacktestingSettings
from .engine import BacktestEngine
from .models import WalkForwardResult, WalkForwardSummary, WalkForwardWindow
from .strategy import EmaCrossoverStrategy


@dataclass(slots=True)
class WalkForwardValidator:
    settings: BacktestingSettings
    engine: BacktestEngine

    def run(
        self,
        frame: pd.DataFrame,
        *,
        strategy: EmaCrossoverStrategy,
        symbol: str,
        timeframe: str,
    ) -> WalkForwardResult:
        windows = self._windows(frame)
        results: list[WalkForwardWindow] = []

        for train_start, train_end, test_start, test_end in windows:
            combined = frame.iloc[train_start:test_end].copy()
            evaluation_start = frame.index[test_start]
            result = self.engine.run(
                combined,
                strategy=strategy,
                symbol=symbol,
                timeframe=timeframe,
                evaluation_start=evaluation_start,
            )
            results.append(
                WalkForwardWindow(
                    train_start=frame.index[train_start].to_pydatetime(),
                    train_end=frame.index[train_end - 1].to_pydatetime(),
                    test_start=frame.index[test_start].to_pydatetime(),
                    test_end=frame.index[test_end - 1].to_pydatetime(),
                    result=result,
                )
            )

        compounded = 1.0
        sharpe_values: list[float] = []
        window_returns: list[float] = []
        drawdowns: list[float] = []
        warnings: list[str] = []

        for window in results:
            compounded *= 1 + window.result.metrics.total_return_fraction
            sharpe_values.append(window.result.metrics.sharpe_ratio)
            window_returns.append(window.result.metrics.total_return_fraction)
            drawdowns.append(window.result.metrics.max_drawdown_fraction)
            warnings.extend(window.result.metrics.warnings)

        summary = WalkForwardSummary(
            window_count=len(results),
            compounded_return_fraction=compounded - 1,
            average_sharpe_ratio=(sum(sharpe_values) / len(sharpe_values)) if sharpe_values else 0.0,
            median_window_return_fraction=median(window_returns) if window_returns else 0.0,
            worst_window_drawdown_fraction=min(drawdowns) if drawdowns else 0.0,
            warnings=list(dict.fromkeys(warnings)),
        )

        return WalkForwardResult(
            strategy_name=strategy.name,
            symbol=symbol,
            timeframe=timeframe,
            summary=summary,
            windows=results,
        )

    def _windows(self, frame: pd.DataFrame) -> list[tuple[int, int, int, int]]:
        total = len(frame)
        train = self.settings.train_bars
        test = self.settings.test_bars

        if total < train + test:
            raise ValueError("Not enough bars for walk-forward validation.")

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
