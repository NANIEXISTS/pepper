from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import ccxt.async_support as ccxt_async

from ..core.enums import OrderStatus
from ..core.models import ExecutionReport, OrderIntent
from ..settings import ExchangeSettings
from .router import OrderRouter


@dataclass(slots=True)
class CcxtLiveOrderRouter(OrderRouter):
    settings: ExchangeSettings
    enabled: bool = False

    async def submit_order(self, order: OrderIntent) -> ExecutionReport:
        if not self.enabled:
            raise RuntimeError("Live trading is disabled. Keep paper trading active until verification gates pass.")
        if not self.settings.api_key or not self.settings.api_secret:
            raise RuntimeError("Live trading requires exchange API credentials loaded from .env.")

        exchange_class = getattr(ccxt_async, self.settings.exchange_id, None)
        if exchange_class is None:
            raise RuntimeError(f"Unsupported ccxt exchange: {self.settings.exchange_id}")

        exchange = exchange_class(
            {
                "apiKey": self.settings.api_key,
                "secret": self.settings.api_secret,
                "password": self.settings.api_password,
                "enableRateLimit": True,
            }
        )
        try:
            if self.settings.sandbox and hasattr(exchange, "set_sandbox_mode"):
                exchange.set_sandbox_mode(True)

            await exchange.load_markets()

            has_create_order = bool(exchange.has.get("createOrder"))
            if not has_create_order:
                raise RuntimeError(
                    f"Exchange capability check failed: {self.settings.exchange_id} does not report createOrder support."
                )

            params: dict[str, Any] = {}
            price = order.entry_price if order.order_type.value == "limit" else None
            created = await exchange.create_order(
                order.symbol,
                order.order_type.value,
                order.side.value,
                order.quantity,
                price,
                params,
            )
            return ExecutionReport(
                order_id=str(created.get("id", f"live-{uuid4().hex[:12]}")),
                status=OrderStatus.ACCEPTED,
                router=f"ccxt:{self.settings.exchange_id}",
                submitted_at=datetime.now(UTC),
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                message="Live order submitted through ccxt.",
                fill_price=float(created.get("price") or 0.0) or None,
            )
        finally:
            await exchange.close()
