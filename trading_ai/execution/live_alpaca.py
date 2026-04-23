from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from ..core.enums import OrderStatus
from ..core.models import ExecutionReport, OrderIntent
from ..settings import AlpacaSettings
from ..venues import is_probable_crypto_symbol, normalize_alpaca_symbol
from .router import OrderRouter


@dataclass(slots=True)
class AlpacaLiveOrderRouter(OrderRouter):
    settings: AlpacaSettings
    enabled: bool = False

    async def submit_order(self, order: OrderIntent) -> ExecutionReport:
        if not self.enabled:
            raise RuntimeError("Live trading is disabled. Keep paper trading active until verification gates pass.")
        if not self.settings.api_key or not self.settings.api_secret:
            raise RuntimeError("Alpaca live routing requires API credentials loaded from .env.")

        is_crypto = is_probable_crypto_symbol(order.symbol)
        payload = {
            "symbol": normalize_alpaca_symbol(order.symbol),
            "qty": str(order.quantity),
            "side": order.side.value,
            "type": order.order_type.value,
            "time_in_force": self.settings.crypto_time_in_force if is_crypto else self.settings.equity_time_in_force,
        }
        if order.order_type.value == "limit":
            payload["limit_price"] = str(order.entry_price)

        base_url = self.settings.live_trading_base_url.rstrip("/")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{base_url}/v2/orders",
                json=payload,
                headers={
                    "APCA-API-KEY-ID": self.settings.api_key,
                    "APCA-API-SECRET-KEY": self.settings.api_secret,
                },
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text.strip() or str(exc)
                raise RuntimeError(
                    f"Alpaca order request failed with {exc.response.status_code}: {detail}"
                ) from exc
            created = response.json()

        fill_price = created.get("filled_avg_price")
        return ExecutionReport(
            order_id=str(created.get("id", f"alpaca-{uuid4().hex[:12]}")),
            status=OrderStatus.ACCEPTED,
            router="alpaca",
            submitted_at=datetime.now(UTC),
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            message="Live order submitted through Alpaca.",
            fill_price=float(fill_price) if fill_price not in (None, "") else None,
        )
