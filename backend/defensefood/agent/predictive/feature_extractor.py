"""
Feature extraction for the predictive subsystem (Phase 1 implementation).

Reads from ``state.scored_history`` (built in Phase 0) and produces a feature
vector for one (lane, period) that respects causality: only data with
``period_observed <= period`` ends up in the vector. The forecaster then
predicts the lane's CVS at ``period + 1`` using this vector as input.

Engineered features land in ``CorridorFeatureVector.derived`` so the dataclass
shape stays stable while we iterate on feature design.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CorridorFeatureVector:
    """A point-in-time feature vector for one corridor.

    Base fields mirror the scored snapshot. Engineered features (rolling
    means, deltas, peer z-scores, cadence shape) live in ``derived``.
    """

    commodity_hs: str
    destination_m49: int
    origin_m49: int
    period: int

    # Structural metrics (Section 2).
    bdi: Optional[float] = None
    ocs: Optional[float] = None
    hhi: Optional[float] = None
    idr: Optional[float] = None
    sci: Optional[float] = None
    sci_norm: Optional[float] = None

    # Hazard / notification side.
    notification_count: int = 0
    severity_total: Optional[float] = None
    his: Optional[float] = None
    hdi: Optional[float] = None

    # Composite.
    cvs: Optional[float] = None
    cvs_mode: Optional[str] = None

    # Categorical context.
    market_presence: Optional[str] = None
    provenance: Optional[str] = None

    # Engineered features. Keys documented in :func:`extract_corridor_features`.
    derived: dict[str, Any] = field(default_factory=dict)


# ── helpers ───────────────────────────────────────────────────────────────


def _f(d: Any, k: str) -> Optional[float]:
    """Coerce ``d[k]`` to a finite float or return None."""
    if not isinstance(d, dict):
        return None
    v = d.get(k)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _lane_history_up_to(
    state: Any, lane_key: tuple[str, int, int], period: int
) -> list[dict[str, Any]]:
    """Return scored entries for ``lane_key`` at every period ≤ ``period``,
    ascending. Empty when the lane has no history."""
    history = getattr(state, "scored_history", None) or {}
    out: list[dict[str, Any]] = []
    for p in sorted(history.keys()):
        if int(p) > int(period):
            continue
        snap = history.get(p) or {}
        entry = snap.get(lane_key)
        if entry is not None:
            out.append(entry)
    return out


def _peer_cvs_distribution(
    state: Any, commodity_hs: str, destination_m49: int, period: int
) -> list[float]:
    """All CVS values at ``period`` for lanes in the same HS-2 chapter into
    the same destination, EXCLUDING the target lane. Used for z-score
    normalisation."""
    history = getattr(state, "scored_history", None) or {}
    snap = history.get(int(period)) or {}
    chapter = str(commodity_hs or "")[:2]
    if not chapter:
        return []
    out: list[float] = []
    for (hs, dest, _origin), entry in snap.items():
        if str(hs)[:2] != chapter:
            continue
        if int(dest) != int(destination_m49):
            continue
        # Exclude the target lane.
        if str(hs) == str(commodity_hs):
            continue
        v = _f(entry, "cvs")
        if v is not None:
            out.append(v)
    return out


def _z(x: Optional[float], population: list[float]) -> Optional[float]:
    """Z-score x against a population. Returns None when sample is too small
    or std is degenerate."""
    if x is None or len(population) < 2:
        return None
    try:
        mu = statistics.mean(population)
        sigma = statistics.pstdev(population)
    except statistics.StatisticsError:
        return None
    if sigma <= 1e-9:
        return None
    return (x - mu) / sigma


def _cadence_shape(counts: list[int]) -> str:
    """Categorise a per-period notification count sequence.

    - "absent"    : all zero.
    - "spiky"     : at least one period > 2× the mean of the others.
    - "decaying"  : monotonically non-increasing across the last 3 points.
    - "rising"    : monotonically non-decreasing across the last 3 points.
    - "steady"    : everything else.
    """
    if not counts or all(c == 0 for c in counts):
        return "absent"
    if len(counts) >= 2:
        last_3 = counts[-3:]
        if len(last_3) >= 2:
            non_dec = all(b >= a for a, b in zip(last_3, last_3[1:]))
            non_inc = all(b <= a for a, b in zip(last_3, last_3[1:]))
            if non_inc and not non_dec:
                return "decaying"
            if non_dec and not non_inc:
                return "rising"
    # Spike detection: any single period > 2x the mean of the rest.
    n = len(counts)
    if n >= 2:
        for i in range(n):
            others = counts[:i] + counts[i + 1:]
            others_mean = statistics.mean(others) if others else 0.0
            if counts[i] > 2.0 * max(others_mean, 0.5):
                return "spiky"
    return "steady"


# ── public extractor ──────────────────────────────────────────────────────


def extract_corridor_features(
    state: Any,
    *,
    commodity_hs: str,
    destination_m49: int,
    origin_m49: int,
    period: int,
) -> Optional[CorridorFeatureVector]:
    """Build the feature vector for one (lane, period).

    Returns ``None`` when the lane has no scored entry at ``period``. Reads
    ONLY periods ≤ ``period`` from state so the result is causal — safe to
    feed into a forecaster predicting ``period + 1``.

    Engineered features written to ``derived`` (all keys may be absent when
    the underlying sequence is too short or NaN-laden):

    Period-anchored:
    - ``commodity_chapter``       : HS-2 chapter (string)
    - ``years_of_history``        : count of prior populated periods (int)
    - ``periods_observed``        : sorted list of populated periods (list[int])

    Rolling and delta:
    - ``cvs_rolling_mean_3``      : mean CVS over the last 3 populated periods
    - ``cvs_delta_yoy``           : cvs_t − cvs_{t-1}
    - ``cvs_delta_2y``            : cvs_t − cvs_{t-2}
    - ``his_rolling_mean_3``      : mean HIS over the last 3 populated periods
    - ``his_delta_yoy``           : his_t − his_{t-1}
    - ``sci_delta_yoy``           : sci_t − sci_{t-1}
    - ``ocs_delta_yoy``           : ocs_t − ocs_{t-1}
    - ``bdi_delta_yoy``           : bdi_t − bdi_{t-1}
    - ``hhi_delta_yoy``           : hhi_t − hhi_{t-1}
    - ``idr_delta_yoy``           : idr_t − idr_{t-1}
    - ``notif_delta_yoy``         : notification_count_t − notification_count_{t-1}

    Notification dynamics:
    - ``notif_cadence_shape``     : "absent" | "spiky" | "decaying" | "rising" | "steady"
    - ``notif_rolling_mean_3``    : mean count over the last 3 populated periods
    - ``notif_cumulative``        : sum of counts over the populated history

    Peer-relative (HS-2 chapter × destination, same period):
    - ``cvs_z_peer``              : (cvs_t − chapter_mean_t) / chapter_std_t
    - ``his_z_peer``              : analogous for HIS
    - ``peer_count``              : how many peers the z-score was computed against

    Volume:
    - ``bilateral_log_kg``        : log10(1 + bilateral_import_kg)
    - ``volume_yoy_pct``          : (vol_t − vol_{t-1}) / max(vol_{t-1}, 1)

    Categorical flags (already on base record but copied here for ML):
    - ``idr_above_1``             : bool
    - ``cvs_mode``                : "sci_crs_his" | "sci_his" | None
    """
    history = getattr(state, "scored_history", None) or {}
    snap = history.get(int(period)) or {}
    lane_key = (str(commodity_hs), int(destination_m49), int(origin_m49))
    entry = snap.get(lane_key)
    if entry is None:
        return None

    # Causal history sequence — strictly ≤ period.
    seq = _lane_history_up_to(state, lane_key, int(period))
    # The current period is the last element of seq by construction.

    # Build base feature vector.
    fv = CorridorFeatureVector(
        commodity_hs=str(commodity_hs),
        destination_m49=int(destination_m49),
        origin_m49=int(origin_m49),
        period=int(period),
        bdi=_f(entry, "bdi"),
        ocs=_f(entry, "ocs"),
        hhi=_f(entry, "hhi"),
        idr=_f(entry, "idr"),
        sci=_f(entry, "sci"),
        sci_norm=_f(entry, "sci_norm"),
        notification_count=int(entry.get("notification_count") or 0),
        severity_total=_f(entry, "severity_total"),
        his=_f(entry, "his"),
        hdi=_f(entry, "hdi"),
        cvs=_f(entry, "cvs"),
        cvs_mode=entry.get("cvs_mode"),
        market_presence=entry.get("market_presence"),
        provenance=entry.get("provenance"),
        derived={},
    )

    # Engineered features. Every key is best-effort: missing data leaves the
    # key absent (NOT a zero) so downstream models can encode the absence.
    derived: dict[str, Any] = {}
    derived["commodity_chapter"] = str(commodity_hs)[:2]
    derived["years_of_history"] = max(len(seq) - 1, 0)
    derived["periods_observed"] = [int(e.get("period") or 0) for e in seq]

    def _series(key: str) -> list[float]:
        return [v for v in (_f(e, key) for e in seq) if v is not None]

    cvs_series = _series("cvs")
    his_series = _series("his")
    sci_series = _series("sci")
    ocs_series = _series("ocs")
    bdi_series = _series("bdi")
    hhi_series = _series("hhi")
    idr_series = _series("idr")

    if len(cvs_series) >= 1:
        derived["cvs_rolling_mean_3"] = statistics.mean(cvs_series[-3:])
    if len(cvs_series) >= 2:
        derived["cvs_delta_yoy"] = cvs_series[-1] - cvs_series[-2]
    if len(cvs_series) >= 3:
        derived["cvs_delta_2y"] = cvs_series[-1] - cvs_series[-3]
    if len(his_series) >= 1:
        derived["his_rolling_mean_3"] = statistics.mean(his_series[-3:])
    if len(his_series) >= 2:
        derived["his_delta_yoy"] = his_series[-1] - his_series[-2]
    if len(sci_series) >= 2:
        derived["sci_delta_yoy"] = sci_series[-1] - sci_series[-2]
    if len(ocs_series) >= 2:
        derived["ocs_delta_yoy"] = ocs_series[-1] - ocs_series[-2]
    if len(bdi_series) >= 2:
        derived["bdi_delta_yoy"] = bdi_series[-1] - bdi_series[-2]
    if len(hhi_series) >= 2:
        derived["hhi_delta_yoy"] = hhi_series[-1] - hhi_series[-2]
    if len(idr_series) >= 2:
        derived["idr_delta_yoy"] = idr_series[-1] - idr_series[-2]

    # Notification dynamics.
    notif_series = [int(e.get("notification_count") or 0) for e in seq]
    derived["notif_cadence_shape"] = _cadence_shape(notif_series)
    if notif_series:
        derived["notif_rolling_mean_3"] = sum(notif_series[-3:]) / min(len(notif_series), 3)
        derived["notif_cumulative"] = sum(notif_series)
    if len(notif_series) >= 2:
        derived["notif_delta_yoy"] = notif_series[-1] - notif_series[-2]

    # Peer-relative — same chapter × destination at the same period.
    peer_cvs = _peer_cvs_distribution(state, commodity_hs, destination_m49, int(period))
    derived["peer_count"] = len(peer_cvs)
    z_cvs = _z(fv.cvs, peer_cvs)
    if z_cvs is not None:
        derived["cvs_z_peer"] = z_cvs
    # HIS z-score requires the same peer slicing.
    peer_his: list[float] = []
    period_snap = history.get(int(period)) or {}
    chapter = str(commodity_hs)[:2]
    for (hs, dest, _origin), other in period_snap.items():
        if str(hs)[:2] != chapter or int(dest) != int(destination_m49):
            continue
        if str(hs) == str(commodity_hs):
            continue
        v = _f(other, "his")
        if v is not None:
            peer_his.append(v)
    z_his = _z(fv.his, peer_his)
    if z_his is not None:
        derived["his_z_peer"] = z_his

    # Volume features.
    bilateral_series = [
        _f(e, "bilateral_import_kg") for e in seq
    ]
    bilateral_series_clean = [v for v in bilateral_series if v is not None]
    if bilateral_series_clean:
        derived["bilateral_log_kg"] = math.log10(1.0 + bilateral_series_clean[-1])
    if len(bilateral_series_clean) >= 2:
        prev = bilateral_series_clean[-2]
        curr = bilateral_series_clean[-1]
        derived["volume_yoy_pct"] = (curr - prev) / max(prev, 1.0)

    # Categorical flags.
    if entry.get("idr_gt_1") is not None:
        derived["idr_above_1"] = bool(entry.get("idr_gt_1"))

    fv.derived = derived
    return fv


__all__ = ["CorridorFeatureVector", "extract_corridor_features"]
