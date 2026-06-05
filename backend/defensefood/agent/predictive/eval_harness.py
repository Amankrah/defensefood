"""
Back-test harness (Phase 5.4 scaffold).

Trains-on-history, evaluates-on-held-out-period. Not implemented; the
shapes are here so the future epic can drop in a real model and the
existing dashboard / admin tooling can render its outputs without
changing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from defensefood.agent.predictive.forecaster import Forecaster


@dataclass
class BackTestCase:
    """One held-out evaluation point."""

    commodity_hs: str
    destination_m49: int
    origin_m49: int
    train_periods: list[int]
    target_period: int
    actual_cvs: float | None = None
    predicted_cvs: float | None = None
    error: float | None = None
    direction_match: bool | None = None


@dataclass
class BackTestResult:
    """Summary of a single back-test run."""

    forecaster_name: str
    cases: list[BackTestCase] = field(default_factory=list)
    mae: float | None = None  # mean absolute CVS error
    rmse: float | None = None  # root mean squared CVS error
    direction_accuracy: float | None = None
    notes: list[str] = field(default_factory=list)


def run_backtest(
    state: Any,
    *,
    forecaster: Forecaster,
    train_periods: list[int],
    target_period: int,
    lane_keys: list[tuple[str, int, int]] | None = None,
) -> BackTestResult:
    """Run a single back-test and aggregate accuracy stats.

    Not yet implemented. Future epic will:
    1. Build CorridorFeatureVector lists for each lane over train_periods.
    2. Call forecaster.predict on each to get a target_period reading.
    3. Compare to the actual target_period CVS from dependency_history.
    4. Aggregate MAE, RMSE, direction accuracy.
    """
    raise NotImplementedError(
        "Phase 5.4 scaffold only. Implementation is the predictive epic."
    )


__all__ = ["BackTestCase", "BackTestResult", "run_backtest"]
