from __future__ import annotations

import numpy as np

from trading_ai.reinforcement import ExecutionTimingCoordinator, ExecutionTimingEnv
from trading_ai.settings import ReinforcementSettings


def test_execution_timing_env_resets_and_steps() -> None:
    env = ExecutionTimingEnv(ReinforcementSettings(enabled=True))
    observation, info = env.reset()
    assert observation.shape == (4,)
    assert info["episode_length"] == 24

    next_observation, reward, terminated, truncated, info = env.step(1)
    assert next_observation.shape == (4,)
    assert isinstance(reward, float)
    assert truncated is False
    assert "inventory_fraction" in info


def test_execution_timing_coordinator_chooses_market_under_urgency() -> None:
    coordinator = ExecutionTimingCoordinator(ReinforcementSettings(enabled=True))
    decision = coordinator.choose_order_type(spread_bps=0.5, time_remaining_fraction=0.05, urgency=0.9)
    assert decision.order_type.value == "market"
