"""
Feature extraction for the predictive subsystem (Phase 5.4 scaffold).

Builds per-corridor, multi-period feature vectors a forecaster can ingest.
The current implementation produces the shape only; populating the values
is the future epic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CorridorFeatureVector:
    """A point-in-time feature vector for one corridor.

    The shape is intentionally close to what ``dependency_history`` already
    carries (so the extractor is a thin wrapper rather than a separate
    pipeline). The future forecaster ingests sequences of these per lane.
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

    # Catch-all for engineered features the future epic adds (rolling means,
    # period-over-period deltas, peer-relative z-scores, etc).
    derived: dict[str, Any] = field(default_factory=dict)


def extract_corridor_features(
    state: Any,
    *,
    commodity_hs: str,
    destination_m49: int,
    origin_m49: int,
    period: int,
) -> Optional[CorridorFeatureVector]:
    """Build a feature vector for one (lane, period).

    Not yet implemented for derived features. The base fields are read
    directly from ``state.dependency_history[period][key]`` plus the
    corresponding ``corridor_metrics`` record. Returns ``None`` when the
    lane has no dependency snapshot for the given period.
    """
    history = getattr(state, "dependency_history", None) or {}
    snap = history.get(int(period)) or {}
    key = (str(commodity_hs), int(destination_m49), int(origin_m49))
    entry = snap.get(key)
    if entry is None:
        return None

    corridor = next(
        (
            c
            for c in state.corridor_metrics
            if str(c.get("commodity_hs")) == str(commodity_hs)
            and int(c.get("destination_m49") or -1) == int(destination_m49)
            and int(c.get("origin_m49") or -1) == int(origin_m49)
        ),
        None,
    )

    def _f(d: dict[str, Any], k: str) -> Optional[float]:
        v = d.get(k)
        try:
            f = float(v) if v is not None else None
        except (TypeError, ValueError):
            return None
        return f

    return CorridorFeatureVector(
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
        cvs=_f(entry, "cvs") or (_f(corridor or {}, "cvs") if corridor else None),
        cvs_mode=(corridor or {}).get("cvs_mode") if corridor else None,
        market_presence=(corridor or {}).get("market_presence") if corridor else None,
        provenance=(corridor or {}).get("provenance") if corridor else None,
        derived={},
    )


__all__ = ["CorridorFeatureVector", "extract_corridor_features"]
