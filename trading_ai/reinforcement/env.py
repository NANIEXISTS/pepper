from __future__ import annotations

from dataclasses import dataclass

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from ..settings import ReinforcementSettings


@dataclass(slots=True)
class ExecutionObservation:
    price_change_bps: float
    spread_bps: float
    inventory_fraction: float
    time_remaining_fraction: float


class ExecutionTimingEnv(gym.Env[np.ndarray, int]):
    metadata = {"render_modes": []}

    def __init__(self, settings: ReinforcementSettings) -> None:
        super().__init__()
        self.settings = settings
        self.observation_space = spaces.Box(
            low=np.array([-500.0, 0.0, -1.0, 0.0], dtype=np.float32),
            high=np.array([500.0, settings.max_slippage_bps, 1.0, 1.0], dtype=np.float32),
            dtype=np.float32,
        )
        self.action_space = spaces.Discrete(3)  # wait, passive limit, aggressive market
        self._step_count = 0
        self._inventory_fraction = 0.0

    def reset(self, *, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        super().reset(seed=seed)
        self._step_count = 0
        self._inventory_fraction = 0.0
        observation = np.array([0.0, 1.0, 0.0, 1.0], dtype=np.float32)
        info = {"episode_length": self.settings.episode_length}
        return observation, info

    def step(self, action: int):  # type: ignore[override]
        self._step_count += 1
        time_remaining_fraction = max((self.settings.episode_length - self._step_count) / self.settings.episode_length, 0.0)
        spread_bps = max(self.settings.max_slippage_bps * time_remaining_fraction, 0.5)

        if action == 0:  # wait
            reward = -0.01
        elif action == 1:  # passive limit
            reward = 0.05 - (spread_bps / 1000)
            self._inventory_fraction = min(self._inventory_fraction + 0.1, self.settings.inventory_fraction_limit)
        else:  # market
            reward = -spread_bps / 100
            self._inventory_fraction = min(self._inventory_fraction + 0.25, self.settings.inventory_fraction_limit)

        obs = np.array(
            [
                float(self.np_random.normal(0.0, 5.0)),
                float(spread_bps),
                float(self._inventory_fraction),
                float(time_remaining_fraction),
            ],
            dtype=np.float32,
        )
        terminated = self._step_count >= self.settings.episode_length
        truncated = False
        info = {"inventory_fraction": self._inventory_fraction}
        return obs, float(reward), terminated, truncated, info
