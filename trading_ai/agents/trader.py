from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..core.enums import OrderSide, OrderType, TradeSignal
from ..core.models import OrderIntent
from ..reinforcement import ExecutionTimingCoordinator
from ..settings import PaperTradingSettings, RiskSettings
from .models import AgentContext, StrategyOutput


@dataclass(slots=True)
class TraderAgent:
    risk_settings: RiskSettings
    paper_settings: PaperTradingSettings
    execution_timing: ExecutionTimingCoordinator

    async def run(self, ctx: AgentContext, strategy: StrategyOutput) -> OrderIntent | None:
        if strategy.signal == TradeSignal.HOLD or strategy.confidence < self.paper_settings.signal_confidence_threshold:
            return None

        latest = ctx.features.iloc[-1]
        latest_price = float(latest["close"])
        atr = float(latest["atr_14"]) if pd.notna(latest["atr_14"]) else latest_price * 0.01
        stop_distance = max(atr * 1.5, latest_price * 0.005)

        urgency = strategy.confidence
        spread_bps = max(abs(float(latest["macd_histogram"])) * 100, 0.5)
        timing_decision = self.execution_timing.choose_order_type(
            spread_bps=spread_bps,
            time_remaining_fraction=1.0,
            urgency=urgency,
        )

        if strategy.signal == TradeSignal.BUY:
            risk_budget = ctx.portfolio_equity * self.risk_settings.max_per_trade_risk_fraction
            quantity = min(risk_budget / stop_distance, ctx.available_cash / latest_price)
            if quantity <= 0:
                return None
            return OrderIntent(
                symbol=ctx.symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                entry_price=latest_price,
                stop_loss_price=max(latest_price - stop_distance, 0.01),
                order_type=timing_decision.order_type,
                metadata={
                    "execution_timing_rationale": timing_decision.rationale,
                    "strategy_confidence": strategy.confidence,
                },
            )

        position = ctx.positions.get(ctx.symbol)
        if position is None or position.quantity <= 0:
            return None
        return OrderIntent(
            symbol=ctx.symbol,
            side=OrderSide.SELL,
            quantity=position.quantity,
            entry_price=latest_price,
            stop_loss_price=latest_price + stop_distance,
            order_type=OrderType.MARKET,
            metadata={
                "execution_timing_rationale": "Closing existing position on bearish strategy signal.",
                "strategy_confidence": strategy.confidence,
            },
        )
