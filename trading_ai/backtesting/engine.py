from __future__ import annotations

from dataclasses import dataclass
from math import prod, sqrt

import pandas as pd

from ..settings import BacktestingSettings
from .models import BacktestMetrics, BacktestResult, BacktestTrade, EquityPoint
from .strategy import EmaCrossoverStrategy


@dataclass(slots=True)
class BacktestEngine:
    settings: BacktestingSettings

    def run(
        self,
        frame: pd.DataFrame,
        *,
        strategy: EmaCrossoverStrategy,
        symbol: str,
        timeframe: str,
        evaluation_start: pd.Timestamp | None = None,
    ) -> BacktestResult:
        prepared = self._prepare(frame)
        target_position = strategy.generate_target_position(prepared)
        executed_position = target_position.shift(1).fillna(0.0)
        close_returns = prepared["close"].pct_change().fillna(0.0)
        trade_turnover = executed_position.diff().abs().fillna(executed_position.abs())
        trading_cost = trade_turnover * ((self.settings.transaction_fee_bps + self.settings.slippage_bps) / 10_000)
        strategy_returns = (executed_position * close_returns) - trading_cost

        if evaluation_start is not None:
            evaluation_mask = prepared.index >= evaluation_start
        else:
            evaluation_mask = pd.Series(True, index=prepared.index)

        evaluated_frame = prepared.loc[evaluation_mask].copy()
        evaluated_position = executed_position.loc[evaluation_mask].copy()
        evaluated_returns = strategy_returns.loc[evaluation_mask].copy()

        if evaluated_frame.empty:
            raise ValueError("Evaluation slice is empty; increase lookback or adjust walk-forward windows.")

        equity_curve = self.settings.initial_capital * (1 + evaluated_returns).cumprod()
        equity_series = [
            EquityPoint(timestamp=timestamp.to_pydatetime(), equity=float(value))
            for timestamp, value in equity_curve.items()
        ]

        metrics = self._metrics(
            evaluated_frame=evaluated_frame,
            evaluated_position=evaluated_position,
            evaluated_returns=evaluated_returns,
            equity_curve=equity_curve,
            timeframe=timeframe,
        )
        trades = self._extract_trades(evaluated_frame["close"], evaluated_position)

        return BacktestResult(
            strategy_name=strategy.name,
            symbol=symbol,
            timeframe=timeframe,
            started_at=evaluated_frame.index[0].to_pydatetime(),
            ended_at=evaluated_frame.index[-1].to_pydatetime(),
            metrics=metrics,
            equity_curve=equity_series,
            trades=trades,
        )

    def _prepare(self, frame: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(frame.index, pd.DatetimeIndex):
            raise ValueError("Backtesting requires a DatetimeIndex.")
        if frame.index.tz is None:
            raise ValueError("Backtesting requires timezone-aware timestamps.")
        if frame.index.has_duplicates:
            raise ValueError("Backtesting rejects duplicate timestamps.")
        if not frame.index.is_monotonic_increasing:
            raise ValueError("Backtesting requires time-ordered data.")
        if "close" not in frame.columns:
            raise ValueError("Backtesting requires a close column.")
        return frame.copy()

    def _metrics(
        self,
        *,
        evaluated_frame: pd.DataFrame,
        evaluated_position: pd.Series,
        evaluated_returns: pd.Series,
        equity_curve: pd.Series,
        timeframe: str,
    ) -> BacktestMetrics:
        periods_per_year = self._periods_per_year(timeframe)
        total_return = float((equity_curve.iloc[-1] / self.settings.initial_capital) - 1)
        annualized = float((1 + total_return) ** (periods_per_year / max(len(evaluated_returns), 1)) - 1)

        volatility = float(evaluated_returns.std(ddof=0))
        sharpe_ratio = 0.0
        if volatility > 0:
            sharpe_ratio = float((evaluated_returns.mean() / volatility) * sqrt(periods_per_year))

        rolling_peak = equity_curve.cummax()
        drawdown = (equity_curve / rolling_peak) - 1
        max_drawdown = float(drawdown.min())

        trades = self._extract_trades(evaluated_frame["close"], evaluated_position)
        win_rate = float(sum(1 for trade in trades if trade.pnl_fraction > 0) / len(trades)) if trades else 0.0
        exposure_fraction = float((evaluated_position != 0).mean())
        benchmark_return = float((evaluated_frame["close"].iloc[-1] / evaluated_frame["close"].iloc[0]) - 1)

        warnings: list[str] = []
        if sharpe_ratio > 2.5:
            warnings.append("Sharpe ratio is above 2.5. Review for leakage or overfitting before trusting this result.")
        if len(trades) < 5:
            warnings.append("Trade count is low. This sample is too small to trust.")

        return BacktestMetrics(
            total_return_fraction=total_return,
            annualized_return_fraction=annualized,
            sharpe_ratio=sharpe_ratio,
            max_drawdown_fraction=max_drawdown,
            win_rate=win_rate,
            trade_count=len(trades),
            exposure_fraction=exposure_fraction,
            benchmark_return_fraction=benchmark_return,
            warnings=warnings,
        )

    def _extract_trades(self, close: pd.Series, position: pd.Series) -> list[BacktestTrade]:
        trades: list[BacktestTrade] = []
        current_entry_time: pd.Timestamp | None = None
        current_entry_price: float | None = None
        current_position = 0.0

        for timestamp, new_position in position.items():
            if current_position == 0.0 and new_position != 0.0:
                current_entry_time = timestamp
                current_entry_price = float(close.loc[timestamp])
                current_position = float(new_position)
                continue

            if current_position != 0.0 and new_position == 0.0 and current_entry_time is not None and current_entry_price is not None:
                exit_price = float(close.loc[timestamp])
                pnl_fraction = ((exit_price / current_entry_price) - 1) * current_position
                trades.append(
                    BacktestTrade(
                        entry_time=current_entry_time.to_pydatetime(),
                        exit_time=timestamp.to_pydatetime(),
                        entry_price=current_entry_price,
                        exit_price=exit_price,
                        side="long" if current_position > 0 else "short",
                        position_fraction=abs(current_position),
                        pnl_fraction=float(pnl_fraction),
                        bars_held=int(position.loc[current_entry_time:timestamp].shape[0]),
                    )
                )
                current_entry_time = None
                current_entry_price = None
                current_position = 0.0

        if current_position != 0.0 and current_entry_time is not None and current_entry_price is not None:
            exit_timestamp = position.index[-1]
            exit_price = float(close.iloc[-1])
            pnl_fraction = ((exit_price / current_entry_price) - 1) * current_position
            trades.append(
                BacktestTrade(
                    entry_time=current_entry_time.to_pydatetime(),
                    exit_time=exit_timestamp.to_pydatetime(),
                    entry_price=current_entry_price,
                    exit_price=exit_price,
                    side="long" if current_position > 0 else "short",
                    position_fraction=abs(current_position),
                    pnl_fraction=float(pnl_fraction),
                    bars_held=int(position.loc[current_entry_time:exit_timestamp].shape[0]),
                )
            )

        return trades

    def _periods_per_year(self, timeframe: str) -> int:
        mapping = {
            "5m": 12 * 24 * 365,
            "15m": 4 * 24 * 365,
            "1h": 24 * 365,
            "4h": 6 * 365,
            "1d": 365,
        }
        return mapping.get(timeframe, 365)
