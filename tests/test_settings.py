from __future__ import annotations

from trading_ai.settings import _normalize_settings_keys, TradingSettings


def test_dynaconf_style_uppercase_keys_are_loaded() -> None:
    raw = {
        "PAPER_TRADING": {"signal_confidence_threshold": 0.2},
        "RISK": {"max_per_trade_risk_fraction": 0.02},
    }

    settings = TradingSettings.model_validate(_normalize_settings_keys(raw))

    assert settings.paper_trading.signal_confidence_threshold == 0.2
    assert settings.risk.max_per_trade_risk_fraction == 0.02
