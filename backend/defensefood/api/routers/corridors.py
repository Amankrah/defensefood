"""Corridor endpoints -- the primary entity in the framework."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from defensefood.api.dependencies import AppState, get_state
from defensefood.ingestion.countries import get_country_name

router = APIRouter(prefix="/corridors", tags=["corridors"])


@router.get("")
def list_corridors(
    commodity: Optional[str] = Query(None, description="Filter by HS code"),
    origin: Optional[int] = Query(None, description="Filter by origin M49"),
    destination: Optional[int] = Query(None, description="Filter by destination M49"),
    min_his: Optional[float] = Query(None, description="Minimum HIS threshold"),
    limit: int = Query(100, ge=1, le=1000),
    state: AppState = Depends(get_state),
):
    """List corridors with optional filtering."""
    results = state.corridor_metrics

    if commodity:
        results = [c for c in results if c.get("commodity_hs") == commodity]
    if origin:
        results = [c for c in results if c.get("origin_m49") == origin]
    if destination:
        results = [c for c in results if c.get("destination_m49") == destination]
    if min_his is not None:
        results = [c for c in results if c.get("his", 0) >= min_his]

    # Sort by HIS descending
    results = sorted(results, key=lambda c: c.get("his", 0), reverse=True)

    return {
        "count": len(results),
        "corridors": results[:limit],
    }


@router.get("/top")
def top_corridors(
    n: int = Query(50, ge=1, le=500),
    sort_by: str = Query("his", description="Sort field: his, severity_total, notification_count"),
    state: AppState = Depends(get_state),
):
    """Get top N corridors by vulnerability metric."""
    valid_sorts = {"his", "severity_total", "notification_count", "hdi"}
    if sort_by not in valid_sorts:
        sort_by = "his"

    results = sorted(
        state.corridor_metrics,
        key=lambda c: c.get(sort_by, 0),
        reverse=True,
    )

    return {
        "sort_by": sort_by,
        "count": min(n, len(results)),
        "corridors": results[:n],
    }


@router.get("/{commodity_hs}/{dest_m49}/{origin_m49}")
def get_corridor_profile(
    commodity_hs: str,
    dest_m49: int,
    origin_m49: int,
    state: AppState = Depends(get_state),
):
    """Get full profile for a specific corridor."""
    for c in state.corridor_metrics:
        if (
            c.get("commodity_hs") == commodity_hs
            and c.get("destination_m49") == dest_m49
            and c.get("origin_m49") == origin_m49
        ):
            return c

    return {"error": "Corridor not found"}


@router.get("/{commodity_hs}/{dest_m49}/{origin_m49}/hazard")
def get_corridor_hazard(
    commodity_hs: str,
    dest_m49: int,
    origin_m49: int,
    state: AppState = Depends(get_state),
):
    """Get Section 4 hazard metrics for a corridor."""
    for c in state.corridor_metrics:
        if (
            c.get("commodity_hs") == commodity_hs
            and c.get("destination_m49") == dest_m49
            and c.get("origin_m49") == origin_m49
        ):
            return {
                "commodity_hs": commodity_hs,
                "destination_m49": dest_m49,
                "origin_m49": origin_m49,
                "his": c.get("his", 0),
                "hdi": c.get("hdi", 0),
                "notification_count": c.get("notification_count", 0),
                "severity_total": c.get("severity_total", 0),
            }

    return {"error": "Corridor not found"}
