"""
Corridor data-quality annotations for API / UI transparency.

Explains why Section 2 SCI (and therefore CVS) may be absent even when RASFF
hazard signals exist on a lane.
"""

from __future__ import annotations

import math
from typing import Any, Optional


# Machine-readable reason codes (stable for filters / analytics).
REASON_OK = "ok"
REASON_NO_TRADE_FOOTPRINT = "no_trade_footprint"
REASON_DS_PRIME_ERROR = "ds_prime_error"
REASON_ZERO_DESTINATION_IMPORTS = "zero_destination_imports"
REASON_HHI_UNAVAILABLE = "hhi_unavailable"
REASON_NO_HAZARD_SIGNAL = "no_hazard_signal"

_LABELS: dict[str, str] = {
    REASON_OK: "Structural score available",
    REASON_NO_TRADE_FOOTPRINT: "No Comtrade or production footprint for this lane",
    REASON_DS_PRIME_ERROR: "Balance sheet invalid (DS′ ≤ 0)",
    REASON_ZERO_DESTINATION_IMPORTS: (
        "No destination imports in the trade year — supplier concentration (HHI) cannot be computed"
    ),
    REASON_HHI_UNAVAILABLE: "Import partner mix unavailable (HHI missing)",
    REASON_NO_HAZARD_SIGNAL: "No RASFF hazard signal on this lane",
}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def _sci_unavailable_reason(m: dict) -> Optional[str]:
    """Return a reason code when structural SCI is not available."""
    if not _is_missing(m.get("sci")):
        return REASON_OK

    if m.get("dependency_error"):
        return REASON_DS_PRIME_ERROR

    total_imports = m.get("total_imports_kg")
    bilateral = m.get("bilateral_import_kg")
    production = m.get("production_kg") or 0.0
    has_trade_fields = total_imports is not None or bilateral is not None

    if not has_trade_fields and production <= 0:
        return REASON_NO_TRADE_FOOTPRINT

    if (total_imports or 0.0) <= 0 and (bilateral or 0.0) <= 0:
        return REASON_ZERO_DESTINATION_IMPORTS

    if _is_missing(m.get("hhi")):
        return REASON_HHI_UNAVAILABLE

    return REASON_HHI_UNAVAILABLE


def _data_quality_tier(m: dict, reason: Optional[str]) -> str:
    """Coarse lane readiness: full structural score vs hazard-only vs none."""
    if m.get("cvs") is not None:
        return "full"
    if reason == REASON_OK and not _is_missing(m.get("sci_norm")):
        return "partial"
    if m.get("cvs_hazard_only") is not None or (m.get("his") or 0) > 0:
        return "hazard_only"
    if reason in (REASON_NO_TRADE_FOOTPRINT, REASON_NO_HAZARD_SIGNAL):
        return "unavailable"
    return "hazard_only"


def annotate_corridor_data_quality(m: dict) -> dict:
    """Attach ``sci_unavailable_reason``, ``sci_unavailable_label``, ``data_quality``."""
    reason = _sci_unavailable_reason(m)
    if reason == REASON_OK and _is_missing(m.get("sci_norm")) and m.get("cvs") is None:
        # Enriched SCI but percentile / CVS not composed (should be rare).
        reason = REASON_HHI_UNAVAILABLE

    if m.get("cvs") is not None:
        reason = REASON_OK

    m["sci_unavailable_reason"] = None if reason == REASON_OK else reason
    m["sci_unavailable_label"] = None if reason == REASON_OK else _LABELS.get(reason, reason)
    m["data_quality"] = _data_quality_tier(m, reason)
    return m


def annotate_corridors_data_quality(corridors: list[dict]) -> list[dict]:
    """Annotate every corridor dict in place; returns the same list."""
    for m in corridors:
        annotate_corridor_data_quality(m)
    return corridors


def count_by_reason(corridors: list[dict]) -> dict[str, int]:
    """Summarise ``sci_unavailable_reason`` counts (excluding ok)."""
    out: dict[str, int] = {}
    for m in corridors:
        r = m.get("sci_unavailable_reason")
        if r:
            out[r] = out.get(r, 0) + 1
    return dict(sorted(out.items(), key=lambda x: -x[1]))
