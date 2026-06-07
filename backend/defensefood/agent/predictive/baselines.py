"""
Baseline forecasters — Phase 1 of the predictive epic.

Two implementations of the :class:`Forecaster` Protocol:

- :class:`PersistenceForecaster` : ``CVS_{t+1} = CVS_t``.
- :class:`ChapterMedianForecaster` : predicts the median CVS of the lane's
  HS-2 chapter × destination peer group at the most recent period.

Both expose the same interface as the future LightGBM forecaster: take a
:class:`ForecastInput` and return a :class:`ForecastOutput` with a point
estimate, an 80% interval (when computable), a direction label, and a
short driver list.

The 80% interval is calibrated from training residuals via
:meth:`fit_residuals`. The harness in :mod:`eval_harness` calls
``fit_residuals`` on every walk-forward training fold before predicting on
the held-out fold so the interval reflects the model's actual error
distribution.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Optional

from defensefood.agent.predictive.feature_extractor import CorridorFeatureVector
from defensefood.agent.predictive.forecaster import ForecastInput, ForecastOutput


# Z-score multiplier for an 80% confidence interval under a normal
# residual distribution. Used by all baselines.
_Z80 = 1.282


def _direction_label(delta: Optional[float], tol: float = 0.03) -> str:
    """Translate a CVS delta into a direction bucket."""
    if delta is None:
        return "stable"
    if delta > tol:
        return "rising"
    if delta < -tol:
        return "falling"
    return "stable"


def _coerce_confidence(width: Optional[float]) -> str:
    """Map a CVS interval width to a coarse confidence label."""
    if width is None or not math.isfinite(width):
        return "low"
    if width < 0.1:
        return "high"
    if width < 0.25:
        return "med"
    return "low"


# ── Persistence ──────────────────────────────────────────────────────────


@dataclass
class PersistenceForecaster:
    """Predicts that next period's CVS equals this period's CVS.

    The bias-corrected variant adds the mean residual from the training
    set (``CVS_actual - CVS_predicted``), which can correct for systematic
    drift across the corpus. By default no bias is applied; the harness
    enables it when training data shows non-zero mean residual.
    """

    name: str = "persistence"
    residual_std: Optional[float] = None
    residual_mean: float = 0.0
    z_multiplier: float = _Z80

    def fit_residuals(self, residuals: list[float]) -> None:
        """Calibrate the 80% interval from a list of training residuals
        (``actual - predicted``). Called by the back-test harness once per
        walk before predicting on the held-out period.
        """
        clean = [r for r in residuals if r is not None and math.isfinite(r)]
        if len(clean) < 2:
            self.residual_std = None
            self.residual_mean = 0.0
            return
        self.residual_mean = statistics.mean(clean)
        self.residual_std = statistics.pstdev(clean)

    def predict(self, query: ForecastInput) -> ForecastOutput:
        if not query.history:
            return ForecastOutput(
                target_period=int(query.as_of_period) + 1,
                direction="stable",
                confidence="low",
                notes=["insufficient_history"],
            )
        last = query.history[-1]
        cvs_t = last.cvs
        if cvs_t is None:
            return ForecastOutput(
                target_period=int(query.as_of_period) + 1,
                direction="stable",
                confidence="low",
                notes=["no_cvs_in_history"],
            )

        point = cvs_t  # bias is added below from training residuals
        if self.residual_mean:
            point = point + self.residual_mean
        # Clip to [0, 1].
        point = max(0.0, min(1.0, point))

        low: Optional[float] = None
        high: Optional[float] = None
        width: Optional[float] = None
        if self.residual_std is not None:
            margin = self.z_multiplier * self.residual_std
            low = max(0.0, point - margin)
            high = min(1.0, point + margin)
            width = high - low

        drivers = ["persistence_anchor"]
        if self.residual_mean:
            drivers.append(f"bias_correction:{self.residual_mean:+.3f}")
        last_delta = (
            None
            if len(query.history) < 2 or query.history[-2].cvs is None
            else cvs_t - query.history[-2].cvs
        )
        return ForecastOutput(
            target_period=int(query.as_of_period) + 1,
            cvs_point=point,
            cvs_low=low,
            cvs_high=high,
            his_point=last.his,
            direction=_direction_label(last_delta),
            confidence=_coerce_confidence(width),
            drivers=drivers,
            notes=[],
        )


# ── Chapter median ───────────────────────────────────────────────────────


@dataclass
class ChapterMedianForecaster:
    """Predicts that next period's CVS equals the lane's current
    chapter × destination peer median.

    Useful sanity check: if the model can't beat "everyone in the same
    chapter and destination behaves the same way", feature engineering
    isn't pulling its weight.
    """

    name: str = "chapter_median"
    state: Optional[Any] = field(default=None)
    residual_std: Optional[float] = None
    residual_mean: float = 0.0
    z_multiplier: float = _Z80

    def _peer_median_at(
        self,
        commodity_hs: str,
        destination_m49: int,
        origin_m49: int,
        period: int,
    ) -> Optional[float]:
        """Median CVS of lanes in the same HS-2 chapter × destination at
        ``period``, EXCLUDING the target lane itself.

        Excluding self matters: otherwise an anomalously high lane would
        drag the median upward and the baseline would predict "stay where
        you are", erasing the peer-reversion signal we're trying to use.
        """
        if self.state is None:
            return None
        history = getattr(self.state, "scored_history", None) or {}
        snap = history.get(int(period)) or {}
        chapter = str(commodity_hs)[:2]
        if not chapter:
            return None
        target_key = (str(commodity_hs), int(destination_m49), int(origin_m49))
        peer_values: list[float] = []
        for (hs, dest, origin), entry in snap.items():
            if (str(hs), int(dest), int(origin)) == target_key:
                continue
            if str(hs)[:2] != chapter:
                continue
            if int(dest) != int(destination_m49):
                continue
            v = entry.get("cvs")
            if v is None:
                continue
            try:
                peer_values.append(float(v))
            except (TypeError, ValueError):
                continue
        if not peer_values:
            return None
        return float(statistics.median(peer_values))

    def fit_residuals(self, residuals: list[float]) -> None:
        clean = [r for r in residuals if r is not None and math.isfinite(r)]
        if len(clean) < 2:
            self.residual_std = None
            self.residual_mean = 0.0
            return
        self.residual_mean = statistics.mean(clean)
        self.residual_std = statistics.pstdev(clean)

    def predict(self, query: ForecastInput) -> ForecastOutput:
        if not query.history:
            return ForecastOutput(
                target_period=int(query.as_of_period) + 1,
                direction="stable",
                confidence="low",
                notes=["insufficient_history"],
            )
        last = query.history[-1]
        target_period = int(query.as_of_period) + 1
        peer_median = self._peer_median_at(
            last.commodity_hs,
            last.destination_m49,
            last.origin_m49,
            int(query.as_of_period),
        )
        if peer_median is None:
            return ForecastOutput(
                target_period=target_period,
                direction="stable",
                confidence="low",
                notes=["no_peer_data"],
            )

        point = peer_median + self.residual_mean
        point = max(0.0, min(1.0, point))

        low: Optional[float] = None
        high: Optional[float] = None
        width: Optional[float] = None
        if self.residual_std is not None:
            margin = self.z_multiplier * self.residual_std
            low = max(0.0, point - margin)
            high = min(1.0, point + margin)
            width = high - low

        # Direction is relative to the lane's most recent CVS.
        last_delta = (
            None if last.cvs is None else (point - last.cvs)
        )

        return ForecastOutput(
            target_period=target_period,
            cvs_point=point,
            cvs_low=low,
            cvs_high=high,
            his_point=last.his,
            direction=_direction_label(last_delta),
            confidence=_coerce_confidence(width),
            drivers=[f"chapter_median:{peer_median:.3f}"],
            notes=[],
        )


# ── factory ──────────────────────────────────────────────────────────────


def build_forecaster(name: str, state: Optional[Any] = None) -> Any:
    """Resolve a forecaster by short name. Centralises the registry so the
    CLI and the eval harness agree on names."""
    if name == "persistence":
        return PersistenceForecaster()
    if name == "chapter_median":
        return ChapterMedianForecaster(state=state)
    if name == "lightgbm":
        # Imported lazily so the rest of the predictive surface still works
        # in environments where lightgbm is not installed (e.g. minimal
        # test setups). Asking for "lightgbm" without the dep gives a
        # clear ImportError.
        from defensefood.agent.predictive.lightgbm_forecaster import (
            LightGBMForecaster,
        )
        return LightGBMForecaster()
    if name == "lightgbm_lite":
        # Same model but drops the high-cardinality commodity_hs from
        # the categorical feature list. Useful for the HS-fragmentation
        # ablation experiment after the 2026-06-07 backtest showed the
        # full LightGBM losing to persistence on MAE.
        from defensefood.agent.predictive.lightgbm_forecaster import (
            LightGBMForecaster,
        )
        forecaster = LightGBMForecaster(include_hs_identity=False)
        forecaster.name = "lightgbm_lite"
        return forecaster
    raise ValueError(f"Unknown forecaster name: {name!r}")


__all__ = [
    "ChapterMedianForecaster",
    "PersistenceForecaster",
    "build_forecaster",
]
