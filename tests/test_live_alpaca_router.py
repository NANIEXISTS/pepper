from __future__ import annotations

from dataclasses import dataclass

import pytest

import trading_ai.execution.live_alpaca as alpaca_router_module
from trading_ai.core.enums import OrderSide
from trading_ai.core.models import OrderIntent
from trading_ai.execution.live_alpaca import AlpacaLiveOrderRouter
from trading_ai.settings import AlpacaSettings


@dataclass
class _FakeResponse:
    payload: dict
    status_code: int = 200
    text: str = ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class _FakeAsyncClient:
    def __init__(self, recorder: list[dict], payload: dict, timeout: float) -> None:
        self.recorder = recorder
        self.payload = payload
        self.timeout = timeout

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    async def post(self, url: str, json: dict | None = None, headers: dict | None = None) -> _FakeResponse:
        self.recorder.append({"url": url, "json": json or {}, "headers": headers or {}})
        return _FakeResponse(self.payload)


@pytest.mark.asyncio
async def test_live_alpaca_router_rejects_when_disabled() -> None:
    router = AlpacaLiveOrderRouter(
        settings=AlpacaSettings(api_key="key", api_secret="secret"),
        enabled=False,
    )
    order = OrderIntent(
        symbol="BTC-USD",
        side=OrderSide.BUY,
        quantity=0.01,
        entry_price=100.0,
        stop_loss_price=95.0,
    )

    with pytest.raises(RuntimeError, match="Live trading is disabled"):
        await router.submit_order(order)


@pytest.mark.asyncio
async def test_live_alpaca_router_submits_normalized_order(monkeypatch) -> None:
    recorder: list[dict] = []

    def _factory(*, timeout: float) -> _FakeAsyncClient:
        return _FakeAsyncClient(
            recorder=recorder,
            payload={"id": "order-123", "filled_avg_price": "101.5"},
            timeout=timeout,
        )

    monkeypatch.setattr(alpaca_router_module.httpx, "AsyncClient", _factory)
    router = AlpacaLiveOrderRouter(
        settings=AlpacaSettings(
            api_key="key",
            api_secret="secret",
            live_trading_base_url="https://paper-api.alpaca.markets",
        ),
        enabled=True,
    )
    order = OrderIntent(
        symbol="BTC-USD",
        side=OrderSide.BUY,
        quantity=0.01,
        entry_price=100.0,
        stop_loss_price=95.0,
    )

    report = await router.submit_order(order)

    assert report.router == "alpaca"
    assert report.order_id == "order-123"
    assert recorder[0]["url"] == "https://paper-api.alpaca.markets/v2/orders"
    assert recorder[0]["json"]["symbol"] == "BTC/USD"
    assert recorder[0]["json"]["type"] == "limit"
    assert recorder[0]["json"]["time_in_force"] == "gtc"
