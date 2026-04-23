from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VenueCapability(BaseModel):
    venue_id: str
    venue_kind: Literal["market_data", "broker"]
    transport: str
    configured: bool = False
    requires_auth_for_market_data: bool = False
    supports_market_data: bool = False
    supports_order_routing: bool = False
    supported_timeframes: list[str] = Field(default_factory=list)
    venue_supported_order_types: list[str] = Field(default_factory=list)
    engine_supported_order_types: list[str] = Field(default_factory=list)
    venue_supports_stop_orders: bool = False
    engine_exposes_stop_orders: bool = False
    supports_sandbox: bool = False
    symbol_format: str
    notes: list[str] = Field(default_factory=list)


class VenueCapabilityCatalog(BaseModel):
    configured_provider: str
    data_routing: list[str]
    configured_live_router: str
    venues: list[VenueCapability]
