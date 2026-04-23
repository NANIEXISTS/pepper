from __future__ import annotations

from dataclasses import dataclass
from math import isclose

import pandas as pd

from ..features import FeatureEngineer
from .models import LeakageCheckResult


class LookAheadBiasError(ValueError):
    """Raised when a feature changes when future rows are removed."""


@dataclass(slots=True)
class FeatureLeakageAnalyzer:
    tolerance: float = 1e-9
    max_checkpoints: int = 12

    def assert_no_lookahead(
        self,
        frame: pd.DataFrame,
        engineer: FeatureEngineer,
        feature_columns: list[str] | None = None,
    ) -> LeakageCheckResult:
        self._validate(frame)
        full = engineer.enrich(frame)
        checked_features = feature_columns or [column for column in full.columns if column not in frame.columns]
        if not checked_features:
            raise ValueError("No engineered features were available for leakage checks.")

        checkpoints = self._checkpoint_positions(len(full.index))
        issues: list[str] = []

        for checkpoint in checkpoints:
            timestamp = full.index[checkpoint]
            prefix = frame.iloc[: checkpoint + 1].copy()
            prefix_enriched = engineer.enrich(prefix)

            for feature in checked_features:
                full_value = full.iloc[checkpoint][feature]
                prefix_value = prefix_enriched.iloc[-1][feature]
                if pd.isna(full_value) and pd.isna(prefix_value):
                    continue
                if pd.isna(full_value) != pd.isna(prefix_value):
                    issues.append(
                        f"{feature} changed nullability at {timestamp.isoformat()} after future rows were removed."
                    )
                    continue
                if not isclose(float(full_value), float(prefix_value), rel_tol=self.tolerance, abs_tol=self.tolerance):
                    issues.append(
                        f"{feature} changed at {timestamp.isoformat()} when future rows were removed."
                    )

        if issues:
            raise LookAheadBiasError("; ".join(issues))

        return LeakageCheckResult(
            passed=True,
            checked_features=checked_features,
            checkpoints_checked=len(checkpoints),
            issues=[],
        )

    def _checkpoint_positions(self, total_rows: int) -> list[int]:
        if total_rows < 2:
            return [0]
        step = max(total_rows // self.max_checkpoints, 1)
        checkpoints = list(range(0, total_rows, step))
        if checkpoints[-1] != total_rows - 1:
            checkpoints.append(total_rows - 1)
        return checkpoints[: self.max_checkpoints] if len(checkpoints) > self.max_checkpoints else checkpoints

    def _validate(self, frame: pd.DataFrame) -> None:
        if not isinstance(frame.index, pd.DatetimeIndex):
            raise ValueError("Leakage checks require a DatetimeIndex.")
        if frame.index.tz is None:
            raise ValueError("Leakage checks require timezone-aware timestamps.")
        if frame.index.has_duplicates:
            raise ValueError("Leakage checks require unique timestamps.")
        if not frame.index.is_monotonic_increasing:
            raise ValueError("Leakage checks require time-ordered data.")
