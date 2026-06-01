"""
Research-mode pure helpers.

Pure-Python aggregators used by the /api/v1/research/* endpoints. None of these
mutate state — they read from corridor_metrics (already enriched at startup)
and shape distributions / cohort aggregations for the researcher UI.
"""

from collections import defaultdict
from typing import Iterable, Optional

import math


# Metrics safe to aggregate across corridors.
SUPPORTED_DISTRIBUTION_METRICS = {
    "his",
    "hdi",
    "sci",
    "sci_norm",
    "idr",
    "ocs",
    "hhi",
    "bdi",
    "ssr",
    "cvs",
    "crs",
    "notification_count",
    "severity_total",
}

SUPPORTED_GROUP_BY = {
    "hs_chapter",
    "origin_eu",
    "dest_eu",
    "origin_country",
    "destination_country",
    "provenance",
}

SUPPORTED_AGGREGATIONS = {"mean", "max", "min", "sum", "count", "median"}


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return float("nan")
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


def compute_distribution(values: Iterable[float], bins: int = 20) -> dict:
    """Histogram with percentile markers and summary stats.

    Skips NaN / None / non-finite values. Returns empty bins when no data.
    """
    cleaned: list[float] = []
    for v in values:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isnan(f) or math.isinf(f):
            continue
        cleaned.append(f)

    if not cleaned:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "p25": None,
            "p75": None,
            "p90": None,
            "std": None,
            "bins": [],
        }

    cleaned.sort()
    n = len(cleaned)
    vmin, vmax = cleaned[0], cleaned[-1]
    mean = sum(cleaned) / n
    var = sum((x - mean) ** 2 for x in cleaned) / n
    std = math.sqrt(var)

    bin_count = max(1, int(bins))
    if vmax == vmin:
        hist = [{"x0": vmin, "x1": vmax, "count": n}]
    else:
        width = (vmax - vmin) / bin_count
        edges = [vmin + i * width for i in range(bin_count + 1)]
        edges[-1] = vmax  # avoid float drift
        counts = [0] * bin_count
        for x in cleaned:
            if x >= vmax:
                counts[-1] += 1
                continue
            idx = int((x - vmin) / width)
            counts[idx] += 1
        hist = [
            {"x0": edges[i], "x1": edges[i + 1], "count": counts[i]}
            for i in range(bin_count)
        ]

    return {
        "count": n,
        "min": vmin,
        "max": vmax,
        "mean": mean,
        "median": _percentile(cleaned, 0.5),
        "p25": _percentile(cleaned, 0.25),
        "p75": _percentile(cleaned, 0.75),
        "p90": _percentile(cleaned, 0.9),
        "std": std,
        "bins": hist,
    }


def _group_key(row: dict, key: str, eu_lookup: Optional[set[int]]) -> Optional[str]:
    if key == "hs_chapter":
        hs = str(row.get("commodity_hs", ""))
        return hs[:2] if hs else None
    if key == "origin_eu":
        m49 = row.get("origin_m49")
        if m49 is None or eu_lookup is None:
            return None
        return "EU" if int(m49) in eu_lookup else "Non-EU"
    if key == "dest_eu":
        m49 = row.get("destination_m49")
        if m49 is None or eu_lookup is None:
            return None
        return "EU" if int(m49) in eu_lookup else "Non-EU"
    if key == "origin_country":
        return row.get("origin_country") or None
    if key == "destination_country":
        return row.get("destination_country") or None
    if key == "provenance":
        return row.get("provenance") or "no_trade"
    return None


def compute_cohorts(
    rows: list[dict],
    group_by: list[str],
    metric: str,
    agg: str,
    eu_lookup: Optional[set[int]] = None,
) -> list[dict]:
    """Group rows by one or more keys, aggregate one metric.

    Returns a list of `{group: {...}, count, value}` dicts, sorted by value desc.
    """
    if not group_by:
        return []
    buckets: dict[tuple, list[float]] = defaultdict(list)
    for row in rows:
        key_parts = tuple(_group_key(row, k, eu_lookup) for k in group_by)
        if any(p is None for p in key_parts):
            continue
        v = row.get(metric)
        if v is None:
            if agg == "count":
                buckets[key_parts].append(1.0)
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isnan(f) or math.isinf(f):
            continue
        buckets[key_parts].append(f)

    out: list[dict] = []
    for key_parts, values in buckets.items():
        if not values:
            continue
        if agg == "mean":
            agg_value = sum(values) / len(values)
        elif agg == "max":
            agg_value = max(values)
        elif agg == "min":
            agg_value = min(values)
        elif agg == "sum":
            agg_value = sum(values)
        elif agg == "count":
            agg_value = float(len(values))
        elif agg == "median":
            agg_value = _percentile(sorted(values), 0.5)
        else:
            continue
        group_dict = {k: v for k, v in zip(group_by, key_parts)}
        out.append({"group": group_dict, "count": len(values), "value": agg_value})

    out.sort(key=lambda r: -r["value"])
    return out
