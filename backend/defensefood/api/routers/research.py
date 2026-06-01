"""
Research-mode endpoints under /api/v1/research/*.

Read-only over AppState. Endpoints:

  GET /research/coverage           — data-quality / coverage stats
  GET /research/methodology        — static catalogue of metrics
  GET /research/distributions/{metric} — histogram + summary stats
  GET /research/cohorts            — group-by aggregations
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from defensefood.api.dependencies import AppState, get_state
from defensefood.api.methodology_catalogue import METHODOLOGY, METHODOLOGY_BY_KEY
from defensefood.ingestion.countries import EU27_M49
from defensefood.pipeline.research import (
    SUPPORTED_AGGREGATIONS,
    SUPPORTED_DISTRIBUTION_METRICS,
    SUPPORTED_GROUP_BY,
    compute_cohorts,
    compute_distribution,
)

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/coverage")
def coverage(state: AppState = Depends(get_state)):
    """Return data-quality and coverage diagnostics built once at startup."""
    return state.coverage or {}


@router.get("/methodology")
def methodology(metric: Optional[str] = Query(None)):
    """Return the full methodology catalogue, or a single entry if `metric=` is set."""
    if metric:
        entry = METHODOLOGY_BY_KEY.get(metric)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"Unknown metric: {metric}")
        return entry
    return {"count": len(METHODOLOGY), "entries": METHODOLOGY}


@router.get("/distributions/{metric}")
def distribution(
    metric: str,
    bins: int = Query(20, ge=2, le=100),
    provenance: Optional[str] = Query(
        None, description="Filter corridors by provenance: faostat | trade_only"
    ),
    origin_eu: Optional[bool] = Query(None),
    dest_eu: Optional[bool] = Query(None),
    state: AppState = Depends(get_state),
):
    """Histogram + summary stats for `metric` across all corridors."""
    if metric not in SUPPORTED_DISTRIBUTION_METRICS:
        raise HTTPException(
            status_code=400,
            detail=f"metric must be one of: {sorted(SUPPORTED_DISTRIBUTION_METRICS)}",
        )

    rows = state.corridor_metrics

    if provenance:
        rows = [r for r in rows if r.get("provenance") == provenance]
    if origin_eu is not None:
        rows = [
            r for r in rows
            if (int(r.get("origin_m49") or 0) in EU27_M49) == origin_eu
        ]
    if dest_eu is not None:
        rows = [
            r for r in rows
            if (int(r.get("destination_m49") or 0) in EU27_M49) == dest_eu
        ]

    values = [r.get(metric) for r in rows]
    dist = compute_distribution(values, bins=bins)
    return {
        "metric": metric,
        "bins": dist["bins"],
        "stats": {k: v for k, v in dist.items() if k != "bins"},
        "filters": {
            "provenance": provenance,
            "origin_eu": origin_eu,
            "dest_eu": dest_eu,
        },
    }


@router.get("/cohorts")
def cohorts(
    group_by: str = Query(..., description="Comma-separated keys: hs_chapter,origin_eu,..."),
    metric: str = Query("his"),
    agg: str = Query("mean"),
    state: AppState = Depends(get_state),
):
    """Group-by aggregation over corridor_metrics."""
    keys = [k.strip() for k in group_by.split(",") if k.strip()]
    bad = [k for k in keys if k not in SUPPORTED_GROUP_BY]
    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown group_by keys: {bad}. Allowed: {sorted(SUPPORTED_GROUP_BY)}",
        )
    if metric not in SUPPORTED_DISTRIBUTION_METRICS:
        raise HTTPException(
            status_code=400,
            detail=f"metric must be one of: {sorted(SUPPORTED_DISTRIBUTION_METRICS)}",
        )
    if agg not in SUPPORTED_AGGREGATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"agg must be one of: {sorted(SUPPORTED_AGGREGATIONS)}",
        )

    rows = compute_cohorts(
        state.corridor_metrics,
        group_by=keys,
        metric=metric,
        agg=agg,
        eu_lookup=EU27_M49,
    )
    return {
        "group_by": keys,
        "metric": metric,
        "agg": agg,
        "count": len(rows),
        "rows": rows,
    }
