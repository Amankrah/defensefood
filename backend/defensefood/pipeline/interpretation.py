"""
Server-side plain-language verdict generator.

Mirrors the frontend ``interpret.ts`` but sources its thresholds from the
single source of truth in ``methodology_catalogue.METHODOLOGY``. The dashboard
and any third-party API consumer see the same verdict text for the same value.

Use:
    >>> from defensefood.pipeline.interpretation import interpret_metric
    >>> interpret_metric("idr", 1.181)
    {'verdict': 'Imports exceed supply (re-export hub)', 'band': 'flag',
     'advice': 'Either a trade hub re-exporting most of what arrives, ...'}
"""

from __future__ import annotations

import math
from typing import Any, Optional

from defensefood.api.methodology_catalogue import METHODOLOGY_BY_KEY


def _is_real_number(v: Any) -> bool:
    """Real, finite number — not None, not NaN, not inf."""
    if v is None:
        return False
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return not (math.isnan(f) or math.isinf(f))


def interpret_metric(
    key: str,
    value: Optional[float],
) -> dict[str, Any]:
    """Return ``{verdict, band, advice, label, ok}`` for the given metric value.

    ``ok`` is False when the value is missing / non-finite OR the metric key
    isn't in the catalogue; in that case ``band`` defaults to ``"low"`` and
    ``verdict``/``advice`` carry diagnostic strings rather than raising.
    """
    entry = METHODOLOGY_BY_KEY.get(key)
    if entry is None:
        return {
            "verdict": "Unknown metric",
            "band": "low",
            "advice": None,
            "label": None,
            "ok": False,
        }

    if not _is_real_number(value):
        return {
            "verdict": "Not available",
            "band": "low",
            "advice": None,
            "label": entry.get("name"),
            "ok": False,
        }

    v = float(value)
    bands = entry.get("scale") or []
    for band in bands:
        lo = float(band.get("min", float("-inf")))
        hi = float(band.get("max", float("inf")))
        # min inclusive, max exclusive — matches the catalogue contract.
        if lo <= v < hi:
            return {
                "verdict": band.get("label", "—"),
                "band": band.get("band", "low"),
                "advice": band.get("advice"),
                "label": entry.get("name"),
                "ok": True,
            }

    # Edge: value lies above the highest scale's max (rare; protect against it).
    if bands:
        last = bands[-1]
        return {
            "verdict": last.get("label", "—"),
            "band": last.get("band", "low"),
            "advice": last.get("advice"),
            "label": entry.get("name"),
            "ok": True,
        }

    return {
        "verdict": "No scale defined",
        "band": "low",
        "advice": None,
        "label": entry.get("name"),
        "ok": False,
    }


# Section 2 keys interpret_corridor will scan by default.
_SECTION_2_KEYS = ("ds_prime", "idr", "ocs", "bdi", "hhi", "ssr", "sci")
_HAZARD_KEYS = ("his", "hdi")
_TRADE_KEYS = ("z_uv", "mtd", "delta_hhi")
_CONSUMPTION_KEYS = ("crs",)
_COMPOSITE_KEYS = ("cvs",)

_DEFAULT_KEYS = _SECTION_2_KEYS + _HAZARD_KEYS + _TRADE_KEYS + _CONSUMPTION_KEYS + _COMPOSITE_KEYS


def interpret_corridor(
    metrics: dict[str, Any],
    keys: Optional[tuple[str, ...]] = None,
) -> dict[str, dict[str, Any]]:
    """Run ``interpret_metric`` for every key in ``keys`` that's present.

    ``metrics`` is a flat dict like ``corridor_metrics[i]`` or the ``dependency``
    block from ``/corridors/.../full``. Returns ``{key: {verdict, band, ...}}``.
    """
    out: dict[str, dict[str, Any]] = {}
    scan = keys or _DEFAULT_KEYS
    for k in scan:
        if k in metrics:
            out[k] = interpret_metric(k, metrics[k])
    return out
