from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from ..core.enums import OrderStatus
from ..core.models import ExecutionReport, OrderIntent


class OrderRouter(ABC):
    @abstractmethod
    async def submit_order(self, order: OrderIntent) -> ExecutionReport:
        """Submit an order to a broker or exchange."""


@dataclass(slots=True)
class PaperOrderRouter(OrderRouter):
    name: str = "paper"
    fill_slippage_bps: float = 2.0

    async def submit_order(self, order: OrderIntent) -> ExecutionReport:
        slippage_multiplier = 1 + (self.fill_slippage_bps / 10_000)
        fill_price = order.entry_price * slippage_multiplier if order.side.value == "buy" else order.entry_price / slippage_multiplier
        return ExecutionReport(
            order_id=f"paper-{uuid4().hex[:12]}",
            status=OrderStatus.FILLED,
            router=self.name,
            submitted_at=datetime.now(UTC),
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            message="Paper order filled through simulated router.",
            fill_price=fill_price,
        )


@dataclass(slots=True)
class LiveOrderRouter(OrderRouter):
    name: str = "live"
    enabled: bool = False
    capability_flags: dict[str, bool] = field(default_factory=dict)

    async def submit_order(self, order: OrderIntent) -> ExecutionReport:
        if not self.enabled:
            raise RuntimeError("Live trading is disabled. Keep PAPER_MODE active until paper verification is complete.")
        if not self.capability_flags.get("createOrder", False):
            raise RuntimeError("Exchange capability check failed: createOrder is not available.")
        raise NotImplementedError("Live exchange routing is intentionally not enabled in Phase 1.")
