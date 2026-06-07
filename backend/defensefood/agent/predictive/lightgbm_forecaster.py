"""
Pooled LightGBM forecaster — Phase 2 of the predictive epic.

One gradient-boosted tree model across every corridor in the corpus, with
corridor identity (HS code, destination, origin, chapter) included as
categorical features so the model can learn lane-specific drift without
training one model per lane (which the tiny data scale prohibits).

Three independent models are trained per fit call — one each for quantile
0.1, 0.5, 0.9 — giving a point estimate (q=0.5) and an 80% confidence
interval (q=0.1 to q=0.9) without any post-hoc calibration step.

How it fits into the harness
----------------------------

The forecaster defines a ``fit(state, train_periods)`` method. The harness
calls it once per walk before any ``predict()``. Forecaster instances are
intentionally single-use: the harness builds a fresh instance per walk so
calibration and training never leak across folds.

Training pairs
--------------

For every consecutive period pair (T, T+1) within ``train_periods``:

* feature vector X[i] = ``extract_corridor_features(lane, period=T)``
  (causal — only data ≤ T is used).
* label y[i] = ``state.scored_history[T+1][lane]["cvs"]``.

Rows with ``y`` missing are dropped. Rows with X['cvs'] missing are kept
(lightgbm handles NaN natively).

Feature design choices
----------------------

* Categoricals are integer-encoded; mappings live on the forecaster so
  predict-time encoding matches train-time.
* Unseen categorical values at predict time get a sentinel integer code
  (the size of the mapping at fit time), which lightgbm treats as a new
  level and falls back to the most common direction in the trees.
* ``commodity_hs`` is a high-cardinality categorical; lightgbm handles
  this well via histogram binning.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Optional

from defensefood.agent.predictive.feature_extractor import (
    CorridorFeatureVector,
    extract_corridor_features,
)
from defensefood.agent.predictive.forecaster import ForecastInput, ForecastOutput

logger = logging.getLogger(__name__)


# Numeric features pulled directly from CorridorFeatureVector base fields.
_NUM_BASE_KEYS: tuple[str, ...] = (
    "cvs", "his", "sci", "sci_norm", "ocs", "bdi", "hhi", "idr",
    "notification_count", "severity_total", "hdi",
)

# Numeric features pulled from CorridorFeatureVector.derived.
_NUM_DERIVED_KEYS: tuple[str, ...] = (
    "years_of_history",
    "cvs_rolling_mean_3", "cvs_delta_yoy", "cvs_delta_2y",
    "his_rolling_mean_3", "his_delta_yoy",
    "sci_delta_yoy", "ocs_delta_yoy", "bdi_delta_yoy",
    "hhi_delta_yoy", "idr_delta_yoy",
    "notif_rolling_mean_3", "notif_cumulative", "notif_delta_yoy",
    "cvs_z_peer", "his_z_peer", "peer_count",
    "bilateral_log_kg", "volume_yoy_pct",
)

# Categorical features. Order is contractual — used for both columns AND
# the ``categorical_feature=`` list passed to lightgbm.
#
# The full HS code is a high-cardinality categorical (~120 values across the
# corpus). With only ~5 training periods per lane, each tree leaf sees too
# few examples and the trees memorise lane identity, hurting generalisation.
# ``LightGBMForecaster(include_hs_identity=False)`` drops it from the
# categorical list (keeping ``commodity_chapter``, which has ~20 values).
# Registered as ``"lightgbm_lite"`` in build_forecaster so the CLI can A/B
# against the full ``"lightgbm"`` variant.
_CAT_BASE_KEYS_FULL: tuple[str, ...] = (
    "commodity_hs",
    "destination_m49",
    "origin_m49",
    "cvs_mode",
    "market_presence",
    "provenance",
)
_CAT_BASE_KEYS_LITE: tuple[str, ...] = (
    "destination_m49",
    "origin_m49",
    "cvs_mode",
    "market_presence",
    "provenance",
)
# Maintain backwards compat: legacy callers that imported _CAT_BASE_KEYS get
# the full list.
_CAT_BASE_KEYS: tuple[str, ...] = _CAT_BASE_KEYS_FULL
_CAT_DERIVED_KEYS: tuple[str, ...] = (
    "commodity_chapter",
    "notif_cadence_shape",
    "idr_above_1",
)


def _nan_if_none(v: Any) -> float:
    if v is None:
        return float("nan")
    try:
        f = float(v)
    except (TypeError, ValueError):
        return float("nan")
    if math.isnan(f) or math.isinf(f):
        return float("nan")
    return f


@dataclass
class LightGBMForecaster:
    """Pooled LightGBM forecaster with quantile prediction.

    Configure with the constructor; call ``fit(state, train_periods)``
    before ``predict()``. Re-use is allowed but each ``fit`` re-trains
    from scratch — there is no warm start.
    """

    name: str = "lightgbm"

    # Hyperparameters. Small leaves + few iterations because the corpus is
    # ~5k training rows at full scale; deeper trees overfit.
    num_leaves: int = 15
    learning_rate: float = 0.05
    num_iterations: int = 200
    min_data_in_leaf: int = 5
    min_data_in_bin: int = 1
    random_state: int = 42

    # Quantiles for the prediction interval. (0.1, 0.5, 0.9) gives a
    # symmetric 80% interval.
    quantiles: tuple[float, float, float] = (0.1, 0.5, 0.9)

    # When False, drop ``commodity_hs`` from the categorical feature list.
    # The HS-2 ``commodity_chapter`` derived field still carries chapter
    # identity, but with ~20 values instead of ~120 it doesn't fragment the
    # training set as badly. See ``_CAT_BASE_KEYS_*`` docstring.
    include_hs_identity: bool = True

    # Populated by fit().
    _models: dict[float, Any] = field(default_factory=dict)
    _cat_mappings: dict[str, dict[Any, int]] = field(default_factory=dict)
    _feature_names: list[str] = field(default_factory=list)
    _categorical_indices: list[int] = field(default_factory=list)
    _train_residual_std: Optional[float] = field(default=None)
    _train_mae: Optional[float] = field(default=None)
    _feature_importance: dict[str, float] = field(default_factory=dict)
    _is_fit: bool = False

    # ── feature row construction ─────────────────────────────────────────

    def _cat_base_keys(self) -> tuple[str, ...]:
        return (
            _CAT_BASE_KEYS_FULL if self.include_hs_identity else _CAT_BASE_KEYS_LITE
        )

    def _build_row(
        self, fv: CorridorFeatureVector, *, training: bool
    ) -> list[float]:
        """Flatten one feature vector into a row of numbers.

        When ``training`` is True, unseen categorical values are added to
        the mapping with a fresh integer code. When False, they get the
        size-of-mapping sentinel (lightgbm treats it as a new level).
        """
        row: list[float] = []
        for k in _NUM_BASE_KEYS:
            row.append(_nan_if_none(getattr(fv, k, None)))
        for k in _NUM_DERIVED_KEYS:
            row.append(_nan_if_none(fv.derived.get(k)))

        for k in self._cat_base_keys():
            v = getattr(fv, k, None)
            row.append(float(self._encode_cat(k, v, training=training)))
        for k in _CAT_DERIVED_KEYS:
            v = fv.derived.get(k)
            row.append(float(self._encode_cat(k, v, training=training)))
        return row

    def _encode_cat(self, key: str, value: Any, *, training: bool) -> int:
        """Integer-encode a categorical value; create the mapping at training
        time, fall back to a sentinel at predict time."""
        if value is None:
            # NaN-equivalent sentinel for categoricals.
            return -1
        v_key = str(value)
        mapping = self._cat_mappings.setdefault(key, {})
        if v_key in mapping:
            return mapping[v_key]
        if training:
            code = len(mapping)
            mapping[v_key] = code
            return code
        # Predict time, unseen value → sentinel.
        return len(mapping)

    def _column_names(self) -> list[str]:
        return (
            list(_NUM_BASE_KEYS)
            + list(_NUM_DERIVED_KEYS)
            + list(self._cat_base_keys())
            + list(_CAT_DERIVED_KEYS)
        )

    def _category_columns(self) -> list[int]:
        offset = len(_NUM_BASE_KEYS) + len(_NUM_DERIVED_KEYS)
        n_cat = len(self._cat_base_keys()) + len(_CAT_DERIVED_KEYS)
        return list(range(offset, offset + n_cat))

    # ── training data extraction ─────────────────────────────────────────

    def _extract_training_pairs(
        self, state: Any, train_periods: list[int]
    ) -> tuple[list[list[float]], list[float]]:
        """Build (X, y) training pairs from ``state.scored_history``.

        Pairs are (features-at-T, label-at-T+1) for every (lane, T)
        where both T and T+1 are in ``train_periods`` AND the lane has a
        scored entry at both.
        """
        history = getattr(state, "scored_history", None) or {}
        train_sorted = sorted(set(int(p) for p in train_periods))

        X: list[list[float]] = []
        y: list[float] = []
        for i in range(1, len(train_sorted)):
            prior_period = train_sorted[i - 1]
            next_period = train_sorted[i]
            next_snap = history.get(next_period) or {}
            prior_snap = history.get(prior_period) or {}
            for lane_key, _entry in prior_snap.items():
                actual_next = next_snap.get(lane_key)
                if actual_next is None:
                    continue
                actual_cvs = actual_next.get("cvs")
                if actual_cvs is None:
                    continue
                try:
                    label = float(actual_cvs)
                except (TypeError, ValueError):
                    continue
                fv = extract_corridor_features(
                    state,
                    commodity_hs=lane_key[0],
                    destination_m49=lane_key[1],
                    origin_m49=lane_key[2],
                    period=prior_period,
                )
                if fv is None:
                    continue
                X.append(self._build_row(fv, training=True))
                y.append(label)
        return X, y

    # ── fit + predict ────────────────────────────────────────────────────

    def fit(self, state: Any, train_periods: list[int]) -> None:
        """Train the three quantile models against the training pairs
        derived from ``state.scored_history``.

        Idempotent: calling twice retrains from scratch.
        """
        import lightgbm as lgb  # local import keeps base startup fast
        import numpy as np

        self._models = {}
        self._cat_mappings = {}
        self._feature_importance = {}
        self._train_mae = None
        self._train_residual_std = None
        self._is_fit = False

        X_raw, y_raw = self._extract_training_pairs(state, train_periods)
        if len(X_raw) < 4:
            # Not enough data to train; predict() will return a graceful
            # "model_not_fitted" output.
            logger.warning(
                "LightGBM fit: only %d training pairs across train_periods=%s; "
                "model not fit, predictions will be None.",
                len(X_raw),
                train_periods,
            )
            return

        feature_names = self._column_names()
        cat_indices = self._category_columns()
        self._feature_names = feature_names
        self._categorical_indices = cat_indices

        X = np.array(X_raw, dtype=float)
        y = np.array(y_raw, dtype=float)

        # Clip labels to [0, 1] for stability (CVS is normalised to that
        # range in production).
        y = np.clip(y, 0.0, 1.0)

        # Native ``lgb.train`` Booster API rather than the sklearn wrapper —
        # avoids the optional scikit-learn dependency.
        train_dataset = lgb.Dataset(
            X,
            label=y,
            feature_name=feature_names,
            categorical_feature=cat_indices,
            free_raw_data=False,
        )

        common_params: dict[str, Any] = {
            "objective": "quantile",
            "num_leaves": self.num_leaves,
            "learning_rate": self.learning_rate,
            "min_data_in_leaf": self.min_data_in_leaf,
            "min_data_in_bin": self.min_data_in_bin,
            "seed": self.random_state,
            "verbose": -1,
            "force_col_wise": True,
        }

        # ``categorical_feature`` lives on the Dataset; lgb.train doesn't
        # accept it as a kwarg.
        for q in self.quantiles:
            params = {**common_params, "alpha": q}
            booster = lgb.train(
                params,
                train_dataset,
                num_boost_round=self.num_iterations,
            )
            self._models[q] = booster

        # Feature importance from the median quantile model.
        median_q = 0.5 if 0.5 in self._models else min(
            self._models, key=lambda q: abs(q - 0.5)
        )
        median_model = self._models[median_q]
        importances = list(median_model.feature_importance(importance_type="gain"))
        total = sum(importances) or 1
        self._feature_importance = {
            feature_names[i]: importances[i] / total
            for i in range(len(feature_names))
        }

        # Training MAE on the median quantile.
        train_predictions = median_model.predict(X)
        residuals = y - train_predictions
        self._train_mae = float(np.mean(np.abs(residuals)))
        self._train_residual_std = float(np.std(residuals))
        self._is_fit = True

    def predict(self, query: ForecastInput) -> ForecastOutput:
        if not query.history:
            return ForecastOutput(
                target_period=int(query.as_of_period) + 1,
                direction="stable",
                confidence="low",
                notes=["insufficient_history"],
            )
        if not self._is_fit:
            return ForecastOutput(
                target_period=int(query.as_of_period) + 1,
                direction="stable",
                confidence="low",
                notes=["model_not_fitted"],
            )

        import numpy as np

        last = query.history[-1]
        row = self._build_row(last, training=False)
        X_pred = np.array([row], dtype=float)

        predictions: dict[float, float] = {}
        for q, model in self._models.items():
            predictions[q] = float(model.predict(X_pred)[0])

        median_q = 0.5 if 0.5 in predictions else min(
            predictions, key=lambda q: abs(q - 0.5)
        )
        low_q = min(self.quantiles)
        high_q = max(self.quantiles)

        point = max(0.0, min(1.0, predictions[median_q]))
        low = max(0.0, min(1.0, predictions[low_q]))
        high = max(0.0, min(1.0, predictions[high_q]))
        # Ensure low ≤ point ≤ high.
        low = min(low, point)
        high = max(high, point)

        # Direction relative to the most recent observed CVS.
        last_cvs = last.cvs
        if last_cvs is not None:
            delta = point - float(last_cvs)
            if delta > 0.03:
                direction = "rising"
            elif delta < -0.03:
                direction = "falling"
            else:
                direction = "stable"
        else:
            direction = "stable"

        width = high - low
        if width < 0.1:
            confidence = "high"
        elif width < 0.25:
            confidence = "med"
        else:
            confidence = "low"

        # Top-3 drivers by importance (filtered to non-zero importance).
        drivers = [
            f"{name}:{importance:.3f}"
            for name, importance in sorted(
                self._feature_importance.items(),
                key=lambda kv: -kv[1],
            )
            if importance > 0
        ][:3]

        return ForecastOutput(
            target_period=int(query.as_of_period) + 1,
            cvs_point=point,
            cvs_low=low,
            cvs_high=high,
            his_point=last.his,
            direction=direction,
            confidence=confidence,
            drivers=drivers,
            notes=[],
        )

    # Forecasters often expose fit_residuals for the harness's persistence
    # interval calibration step; LightGBM doesn't need it because the
    # quantile triplet already produces an interval.
    def fit_residuals(self, residuals: list[float]) -> None:  # noqa: D401
        return None


__all__ = ["LightGBMForecaster"]
