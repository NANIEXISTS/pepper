from __future__ import annotations

import pytest

from trading_ai.risk import PositionSizeRequest, PositionSizer


def test_fixed_fractional_sizes_to_stop_distance_when_unbounded_by_cash() -> None:
    sizer = PositionSizer(max_per_trade_risk_fraction=0.01)
    request = PositionSizeRequest(
        equity=100_000.0,
        entry_price=100.0,
        stop_loss_price=98.0,
        atr=1.0,
        available_cash=1_000_000.0,
        mode="fixed_fractional",
    )

    result = sizer.size(request)

    # 1% of 100k = 1000 USD risk; 2 USD per share stop -> 500 shares
    assert result.quantity == pytest.approx(500.0)
    assert result.binding_constraint == "stop_loss_risk"
    assert result.risk_fraction == pytest.approx(0.01)


def test_volatility_targeted_caps_at_atr_target() -> None:
    sizer = PositionSizer(
        max_per_trade_risk_fraction=0.05,
        target_daily_volatility_fraction=0.005,
    )
    request = PositionSizeRequest(
        equity=100_000.0,
        entry_price=100.0,
        stop_loss_price=95.0,  # generous stop, would otherwise allow huge size
        atr=2.0,
        available_cash=1_000_000.0,
        mode="volatility_targeted",
    )

    result = sizer.size(request)

    # vol_quantity = 0.005 * 100_000 / 2.0 = 250
    # stop_quantity = 0.05 * 100_000 / 5 = 1000  -> volatility target is the binding cap
    assert result.quantity == pytest.approx(250.0)
    assert result.binding_constraint == "volatility_target"


def test_available_cash_is_a_hard_cap() -> None:
    sizer = PositionSizer(max_per_trade_risk_fraction=0.5)
    request = PositionSizeRequest(
        equity=100_000.0,
        entry_price=100.0,
        stop_loss_price=99.0,
        atr=0.0,
        available_cash=1_000.0,  # very tight cash
        mode="fixed_fractional",
    )

    result = sizer.size(request)

    assert result.quantity == pytest.approx(10.0)
    assert result.binding_constraint == "available_cash"


def test_zero_stop_distance_returns_no_capacity() -> None:
    sizer = PositionSizer()
    request = PositionSizeRequest(
        equity=100_000.0,
        entry_price=100.0,
        stop_loss_price=100.0,
        atr=0.5,
        mode="fixed_fractional",
    )

    result = sizer.size(request)

    assert result.quantity == 0.0
    assert result.binding_constraint == "no_capacity"


def test_volatility_targeted_requires_positive_atr() -> None:
    sizer = PositionSizer()
    request = PositionSizeRequest(
        equity=100_000.0,
        entry_price=100.0,
        stop_loss_price=98.0,
        atr=0.0,
        mode="volatility_targeted",
    )

    result = sizer.size(request)

    assert result.quantity == 0.0
    assert result.binding_constraint == "no_capacity"
    assert "ATR" in result.rationale
