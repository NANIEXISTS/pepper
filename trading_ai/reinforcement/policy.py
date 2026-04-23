from __future__ import annotations

from dataclasses import dataclass

from ..core.enums import OrderType
from ..settings import ReinforcementSettings


@dataclass(slots=True)
class ExecutionTimingDecision:
    order_type: OrderType
    rationale: str


@dataclass(slots=True)
class ExecutionTimingCoordinator:
    settings: ReinforcementSettings

    def choose_order_type(
        self,
        *,
        spread_bps: float,
        time_remaining_fraction: float,
        urgency: float,
    ) -> ExecutionTimingDecision:
        if not self.settings.enabled:
            return ExecutionTimingDecision(
                order_type=OrderType.LIMIT,
                rationale="RL execution timing disabled; defaulting to passive limit-first behavior.",
            )

        if urgency > 0.8 or time_remaining_fraction < 0.15 or spread_bps < 1.0:
            return ExecutionTimingDecision(
                order_type=OrderType.MARKET,
                rationale="Execution urgency is high enough to cross the spread.",
            )

        return ExecutionTimingDecision(
            order_type=OrderType.LIMIT,
            rationale="Execution timing policy prefers passive liquidity capture.",
        )
