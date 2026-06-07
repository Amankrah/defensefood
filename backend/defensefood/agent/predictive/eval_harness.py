"""
Back-test harness for the predictive subsystem (Phase 1 implementation).

A *walk* is one ``(train_periods, target_period)`` split. The forecaster sees
``train_periods`` worth of history and predicts ``target_period``; we score
against the actual ``CVS`` at ``target_period``. Walking from the earliest
predictable period to the latest gives us multiple folds of evidence.

How the harness is meant to be driven:

1. Pick ``train_periods`` and ``target_period`` (must satisfy ``max(train) +
   1 == target``).
2. Build a fresh forecaster instance (the CLI does this via the
   ``baselines.build_forecaster`` factory).
3. Call :func:`fit_residuals_from_training` to calibrate the 80% interval
   against the training residuals.
4. Call :func:`run_backtest` to predict every eligible lane at
   ``target_period`` and aggregate metrics.

The harness is deliberately the *only* place that knows about train / eval
splits. Forecasters never see future data: they receive a sequence of
:class:`CorridorFeatureVector` strictly ≤ ``as_of_period``.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Optional

from defensefood.agent.predictive.feature_extractor import (
    CorridorFeatureVector,
    extract_corridor_features,
)
from defensefood.agent.predictive.forecaster import (
    ForecastInput,
    ForecastOutput,
    Forecaster,
)


@dataclass
class BackTestCase:
    """One held-out evaluation point."""

    commodity_hs: str
    destination_m49: int
    origin_m49: int
    train_periods: list[int]
    target_period: int
    actual_cvs: Optional[float] = None
    predicted_cvs: Optional[float] = None
    error: Optional[float] = None
    direction_match: Optional[bool] = None
    interval_covers_actual: Optional[bool] = None
    forecast: Optional[ForecastOutput] = None


@dataclass
class BackTestResult:
    """Summary of a single back-test run."""

    forecaster_name: str
    train_periods: list[int]
    target_period: int
    cases: list[BackTestCase] = field(default_factory=list)
    mae: Optional[float] = None
    rmse: Optional[float] = None
    direction_accuracy: Optional[float] = None
    interval_coverage: Optional[float] = None
    n_cases: int = 0
    n_with_label: int = 0
    notes: list[str] = field(default_factory=list)


# ── helpers ──────────────────────────────────────────────────────────────


def _lane_keys_present_at(
    state: Any, period: int
) -> list[tuple[str, int, int]]:
    history = getattr(state, "scored_history", None) or {}
    snap = history.get(int(period)) or {}
    return list(snap.keys())


def _build_history_up_to(
    state: Any, lane_key: tuple[str, int, int], as_of_period: int
) -> list[CorridorFeatureVector]:
    """Sequence of feature vectors for ``lane_key`` from the earliest
    populated period through ``as_of_period`` inclusive.
    """
    history = getattr(state, "scored_history", None) or {}
    periods = sorted(int(p) for p in history.keys() if int(p) <= int(as_of_period))
    out: list[CorridorFeatureVector] = []
    for p in periods:
        snap = history.get(p) or {}
        if lane_key not in snap:
            continue
        fv = extract_corridor_features(
            state,
            commodity_hs=lane_key[0],
            destination_m49=lane_key[1],
            origin_m49=lane_key[2],
            period=p,
        )
        if fv is not None:
            out.append(fv)
    return out


def _direction_from(prev: Optional[float], curr: Optional[float], tol: float = 0.03) -> str:
    if prev is None or curr is None:
        return "stable"
    d = curr - prev
    if d > tol:
        return "rising"
    if d < -tol:
        return "falling"
    return "stable"


# ── public API ───────────────────────────────────────────────────────────


def fit_residuals_from_training(
    state: Any,
    *,
    forecaster: Forecaster,
    train_periods: list[int],
) -> None:
    """Walk every lane in the training periods, predict the within-train next
    period for each, and feed the residuals to ``forecaster.fit_residuals``.

    Forecasters that don't define ``fit_residuals`` are skipped silently
    (the Protocol leaves calibration optional).
    """
    if not hasattr(forecaster, "fit_residuals"):
        return
    train_sorted = sorted(set(int(p) for p in train_periods))
    if len(train_sorted) < 2:
        forecaster.fit_residuals([])  # clears residuals
        return

    residuals: list[float] = []
    history = getattr(state, "scored_history", None) or {}
    # For every adjacent pair within train_periods, predict the later period
    # from the earlier and collect (actual - predicted).
    for i in range(1, len(train_sorted)):
        prior_period = train_sorted[i - 1]
        next_period = train_sorted[i]
        next_snap = history.get(next_period) or {}
        for lane_key in _lane_keys_present_at(state, prior_period):
            actual = next_snap.get(lane_key)
            if actual is None:
                continue
            actual_cvs = actual.get("cvs")
            if actual_cvs is None:
                continue
            seq = _build_history_up_to(state, lane_key, prior_period)
            if not seq:
                continue
            query = ForecastInput(
                commodity_hs=lane_key[0],
                destination_m49=lane_key[1],
                origin_m49=lane_key[2],
                as_of_period=prior_period,
                history=seq,
            )
            try:
                out = forecaster.predict(query)
            except Exception:  # noqa: BLE001 — defensive
                continue
            if out.cvs_point is None:
                continue
            try:
                residuals.append(float(actual_cvs) - float(out.cvs_point))
            except (TypeError, ValueError):
                continue
    forecaster.fit_residuals(residuals)


def run_backtest(
    state: Any,
    *,
    forecaster: Forecaster,
    train_periods: list[int],
    target_period: int,
    lane_keys: Optional[list[tuple[str, int, int]]] = None,
) -> BackTestResult:
    """Run a single back-test fold (one train/target split).

    For each lane that has a scored entry at ``target_period`` AND at least
    one period of history within ``train_periods``, build the feature
    sequence, ask the forecaster to predict, and score against the actual
    ``target_period`` CVS.

    Returns a :class:`BackTestResult` with per-case detail and the four
    summary metrics: MAE, RMSE, direction accuracy, 80% interval coverage.
    """
    train_sorted = sorted(set(int(p) for p in train_periods))
    target_int = int(target_period)
    if train_sorted and max(train_sorted) >= target_int:
        raise ValueError(
            "train_periods must all precede target_period; got "
            f"train={train_sorted}, target={target_int}"
        )

    history = getattr(state, "scored_history", None) or {}
    target_snap = history.get(target_int) or {}

    if lane_keys is None:
        lane_keys = list(target_snap.keys())

    forecaster_name = getattr(forecaster, "name", forecaster.__class__.__name__)
    result = BackTestResult(
        forecaster_name=forecaster_name,
        train_periods=train_sorted,
        target_period=target_int,
    )

    errors: list[float] = []
    direction_hits = 0
    direction_total = 0
    interval_hits = 0
    interval_total = 0

    for lane_key in lane_keys:
        actual = target_snap.get(lane_key)
        if actual is None:
            continue
        actual_cvs = actual.get("cvs")
        # Build the lane's history up to the LATEST training period only.
        seq = _build_history_up_to(state, lane_key, max(train_sorted) if train_sorted else target_int - 1)
        if not seq:
            continue
        # Drop history rows whose period isn't in train_periods so the
        # forecaster only sees in-train data.
        train_set = set(train_sorted)
        seq = [fv for fv in seq if int(fv.period) in train_set]
        if not seq:
            continue

        query = ForecastInput(
            commodity_hs=lane_key[0],
            destination_m49=lane_key[1],
            origin_m49=lane_key[2],
            as_of_period=int(seq[-1].period),
            history=seq,
        )
        try:
            forecast = forecaster.predict(query)
        except Exception as exc:  # noqa: BLE001 — defensive
            case = BackTestCase(
                commodity_hs=lane_key[0],
                destination_m49=lane_key[1],
                origin_m49=lane_key[2],
                train_periods=train_sorted,
                target_period=target_int,
                actual_cvs=(
                    float(actual_cvs) if actual_cvs is not None else None
                ),
            )
            result.cases.append(case)
            result.notes.append(
                f"forecaster raised on {lane_key}: {type(exc).__name__}"
            )
            continue

        case = BackTestCase(
            commodity_hs=lane_key[0],
            destination_m49=lane_key[1],
            origin_m49=lane_key[2],
            train_periods=train_sorted,
            target_period=target_int,
            actual_cvs=float(actual_cvs) if actual_cvs is not None else None,
            predicted_cvs=forecast.cvs_point,
            forecast=forecast,
        )

        if actual_cvs is not None and forecast.cvs_point is not None:
            err = float(forecast.cvs_point) - float(actual_cvs)
            case.error = err
            errors.append(err)

            # Direction accuracy: compare predicted vs actual direction
            # relative to the lane's most-recent CVS in the training set.
            prev_cvs = seq[-1].cvs
            actual_dir = _direction_from(prev_cvs, float(actual_cvs))
            predicted_dir = forecast.direction or "stable"
            case.direction_match = actual_dir == predicted_dir
            if case.direction_match:
                direction_hits += 1
            direction_total += 1

            # 80% interval coverage.
            if forecast.cvs_low is not None and forecast.cvs_high is not None:
                covers = (
                    forecast.cvs_low <= float(actual_cvs) <= forecast.cvs_high
                )
                case.interval_covers_actual = covers
                if covers:
                    interval_hits += 1
                interval_total += 1

        result.cases.append(case)

    result.n_cases = len(result.cases)
    result.n_with_label = len(errors)
    if errors:
        abs_errors = [abs(e) for e in errors]
        result.mae = statistics.mean(abs_errors)
        result.rmse = math.sqrt(statistics.mean(e * e for e in errors))
    if direction_total > 0:
        result.direction_accuracy = direction_hits / direction_total
    if interval_total > 0:
        result.interval_coverage = interval_hits / interval_total

    return result


def prepare_forecaster(
    state: Any, *, forecaster: Any, train_periods: list[int]
) -> None:
    """Run every forecaster-specific training step before the held-out fold.

    Two hooks the harness understands:

    - ``forecaster.fit(state, train_periods)`` — trained-model forecasters
      (LightGBM, future GBDT) implement this to build their model from the
      training fold.
    - ``forecaster.fit_residuals(residuals)`` — baseline forecasters use
      this to calibrate their 80% confidence interval from training
      residuals.

    Both are optional. If a forecaster defines ``fit``, we call it first;
    if it also defines ``fit_residuals``, the harness then collects
    within-train residuals and passes them in. Order matters: residuals
    must be computed with the *fitted* model.
    """
    if hasattr(forecaster, "fit"):
        try:
            forecaster.fit(state, list(train_periods))
        except Exception as exc:  # noqa: BLE001
            # Defensive: a failing fit shouldn't crash the whole walk
            # sequence. The predict() path is expected to gracefully
            # report "model_not_fitted" or similar.
            import logging
            logging.getLogger(__name__).warning(
                "forecaster.fit raised: %s — continuing with un-fit instance",
                exc,
            )

    if hasattr(forecaster, "fit_residuals"):
        fit_residuals_from_training(
            state, forecaster=forecaster, train_periods=train_periods
        )


def walk_forward(
    state: Any,
    *,
    forecaster_factory: Any,
    target_metric: str = "cvs",
    min_train_periods: int = 1,
) -> list[BackTestResult]:
    """Run a sequence of walks across every viable (train_periods, target)
    split in ``state.scored_history``.

    The walk starts at the earliest period that has at least
    ``min_train_periods`` of prior data and proceeds through the latest
    populated period. For each walk a *fresh* forecaster instance is
    obtained from ``forecaster_factory()`` so calibration from previous
    walks doesn't leak.
    """
    if target_metric != "cvs":
        raise ValueError(
            "Phase 1 only supports target_metric='cvs'; got "
            f"{target_metric!r}"
        )

    history = getattr(state, "scored_history", None) or {}
    populated = sorted(int(p) for p, snap in history.items() if snap)
    if len(populated) < min_train_periods + 1:
        return []

    walks: list[BackTestResult] = []
    for i in range(min_train_periods, len(populated)):
        target = populated[i]
        train = populated[:i]
        forecaster = forecaster_factory()
        prepare_forecaster(state, forecaster=forecaster, train_periods=train)
        walks.append(
            run_backtest(
                state,
                forecaster=forecaster,
                train_periods=train,
                target_period=target,
            )
        )
    return walks


__all__ = [
    "BackTestCase",
    "BackTestResult",
    "fit_residuals_from_training",
    "prepare_forecaster",
    "run_backtest",
    "walk_forward",
]
