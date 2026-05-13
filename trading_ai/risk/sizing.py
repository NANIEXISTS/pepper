from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


SizingMode = Literal["fixed_fractional", "volatility_targeted"]


class PositionSizeRequest(BaseModel):
    equity: float = Field(gt=0.0)
    entry_price: float = Field(gt=0.0)
    stop_loss_price: float = Field(gt=0.0)
    atr: float = Field(default=0.0, ge=0.0)
    available_cash: float = Field(default=0.0, ge=0.0)
    mode: SizingMode = "fixed_fractional"


class PositionSizeResult(BaseModel):
    quantity: float = Field(ge=0.0)
    mode: SizingMode
    risk_dollars: float = Field(ge=0.0)
    risk_fraction: float = Field(ge=0.0)
    binding_constraint: Literal[
        "stop_loss_risk",
        "available_cash",
        "volatility_target",
        "no_capacity",
    ]
    rationale: str


@dataclass(slots=True)
class PositionSizer:
    """Compute order quantity using either fixed-fractional or volatility-targeted sizing.

    Both modes are bounded by the configured per-trade risk fraction and by
    available cash. Volatility-targeted sizing additionally caps the position
    so that one ATR of price movement is no more than the daily volatility
    target - useful when volatility regimes shift and stop distance is no
    longer a faithful proxy for portfolio variance.
    """

    max_per_trade_risk_fraction: float = 0.01
    target_daily_volatility_fraction: float = 0.01

    def size(self, request: PositionSizeRequest) -> PositionSizeResult:
        stop_distance = abs(request.entry_price - request.stop_loss_price)
        if stop_distance <= 0:
            return PositionSizeResult(
                quantity=0.0,
                mode=request.mode,
                risk_dollars=0.0,
                risk_fraction=0.0,
                binding_constraint="no_capacity",
                rationale="Stop loss equals entry price; no risk distance to size against.",
            )

        risk_dollars = request.equity * self.max_per_trade_risk_fraction
        stop_quantity = risk_dollars / stop_distance

        candidates: list[tuple[float, str, str]] = [
            (
                stop_quantity,
                "stop_loss_risk",
                f"Risk capped at {self.max_per_trade_risk_fraction:.2%} of equity ({risk_dollars:.2f} USD).",
            )
        ]

        if request.mode == "volatility_targeted":
            if request.atr <= 0:
                return PositionSizeResult(
                    quantity=0.0,
                    mode=request.mode,
                    risk_dollars=0.0,
                    risk_fraction=0.0,
                    binding_constraint="no_capacity",
                    rationale="Volatility-targeted sizing requires a positive ATR estimate.",
                )
            vol_quantity = (self.target_daily_volatility_fraction * request.equity) / request.atr
            candidates.append(
                (
                    vol_quantity,
                    "volatility_target",
                    f"Volatility target {self.target_daily_volatility_fraction:.2%} per ATR move.",
                )
            )

        if request.available_cash > 0:
            cash_quantity = request.available_cash / request.entry_price
            candidates.append(
                (cash_quantity, "available_cash", f"Available cash cap of {request.available_cash:.2f} USD.")
            )

        binding_quantity, binding_constraint, rationale = min(candidates, key=lambda item: item[0])
        binding_quantity = max(binding_quantity, 0.0)
        if binding_quantity <= 0:
            return PositionSizeResult(
                quantity=0.0,
                mode=request.mode,
                risk_dollars=0.0,
                risk_fraction=0.0,
                binding_constraint="no_capacity",
                rationale="No sizing path produced a positive quantity.",
            )

        actual_risk_dollars = stop_distance * binding_quantity
        actual_risk_fraction = actual_risk_dollars / request.equity if request.equity > 0 else 0.0
        return PositionSizeResult(
            quantity=binding_quantity,
            mode=request.mode,
            risk_dollars=actual_risk_dollars,
            risk_fraction=actual_risk_fraction,
            binding_constraint=binding_constraint,  # type: ignore[arg-type]
            rationale=rationale,
        )
