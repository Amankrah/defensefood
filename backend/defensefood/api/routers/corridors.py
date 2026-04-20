"""Corridor endpoints -- the primary entity in the framework."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from defensefood.api.dependencies import AppState, get_state
from defensefood.ingestion.countries import EU27_M49, get_country_name
from defensefood.pipeline.dependency_pipeline import compute_corridor_dependency
from defensefood.pipeline.trade_flow_pipeline import (
    compute_concentration_shifts,
    compute_mirror_discrepancy,
    compute_unit_value_anomalies,
)

router = APIRouter(prefix="/corridors", tags=["corridors"])


@router.get("")
def list_corridors(
    commodity: Optional[str] = Query(None, description="Filter by HS code"),
    origin: Optional[int] = Query(None, description="Filter by origin M49"),
    destination: Optional[int] = Query(None, description="Filter by destination M49"),
    min_his: Optional[float] = Query(None, description="Minimum HIS threshold"),
    active_only: bool = Query(
        False,
        description=(
            "If true, exclude corridors whose destination was only flagged "
            "for_attention (no follow-up, distribution, or notifier role)."
        ),
    ),
    role: Optional[str] = Query(
        None,
        description="Filter to corridors with this role: notifier, distribution, followUp, attention",
    ),
    min_notification_count: Optional[int] = Query(
        None,
        ge=0,
        description="Minimum RASFF notification count on the lane",
    ),
    min_hdi: Optional[float] = Query(
        None,
        description="Minimum hazard diversity index (HDI)",
    ),
    min_cvs: Optional[float] = Query(
        None,
        ge=0,
        le=1,
        description="Minimum combined vulnerability score (lanes without CVS excluded)",
    ),
    has_cvs: Optional[bool] = Query(
        None,
        description="If true, only lanes with a CVS; if false, only lanes without CVS",
    ),
    origin_eu: Optional[bool] = Query(
        None,
        description="If true, EU27 origin only; if false, non-EU origin only",
    ),
    dest_eu: Optional[bool] = Query(
        None,
        description="If true, EU27 destination only; if false, non-EU destination only",
    ),
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
    if active_only:
        results = [c for c in results if c.get("is_active_destination", False)]
    if role:
        results = [c for c in results if role in (c.get("destination_roles") or [])]
    if min_notification_count is not None:
        results = [
            c for c in results if c.get("notification_count", 0) >= min_notification_count
        ]
    if min_hdi is not None:
        results = [c for c in results if c.get("hdi", 0) >= min_hdi]
    if min_cvs is not None:
        results = [
            c
            for c in results
            if c.get("cvs") is not None and float(c["cvs"]) >= min_cvs
        ]
    if has_cvs is True:
        results = [c for c in results if c.get("cvs") is not None]
    elif has_cvs is False:
        results = [c for c in results if c.get("cvs") is None]
    if origin_eu is True:
        results = [c for c in results if c.get("origin_m49") in EU27_M49]
    elif origin_eu is False:
        results = [c for c in results if c.get("origin_m49") not in EU27_M49]
    if dest_eu is True:
        results = [c for c in results if c.get("destination_m49") in EU27_M49]
    elif dest_eu is False:
        results = [c for c in results if c.get("destination_m49") not in EU27_M49]

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
    valid_sorts = {"his", "severity_total", "notification_count", "hdi", "cvs"}
    if sort_by not in valid_sorts:
        sort_by = "his"

    results = sorted(
        state.corridor_metrics,
        key=lambda c: c.get(sort_by, 0) or 0,
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


@router.get("/{commodity_hs}/{dest_m49}/{origin_m49}/full")
def get_corridor_full_profile(
    commodity_hs: str,
    dest_m49: int,
    origin_m49: int,
    state: AppState = Depends(get_state),
):
    """Full forensic profile: Section 2 + 4 + 5 + 7 metrics combined."""
    # Section 4 (hazard) -- from pre-computed state
    hazard = None
    base = None
    for c in state.corridor_metrics:
        if (
            c.get("commodity_hs") == commodity_hs
            and c.get("destination_m49") == dest_m49
            and c.get("origin_m49") == origin_m49
        ):
            base = c
            hazard = {
                "his": c.get("his", 0),
                "hdi": c.get("hdi", 0),
                "notification_count": c.get("notification_count", 0),
                "severity_total": c.get("severity_total", 0),
                "hazard_breakdown": c.get("hazard_breakdown", {}),
            }
            break

    if base is None:
        return {"error": "Corridor not found"}

    # Section 2 (dependency) -- compute from trade data
    dependency = None
    if state.trade_df is not None and not state.trade_df.empty:
        periods = sorted(state.trade_df["period"].unique())
        if periods:
            dep_result = compute_corridor_dependency(
                state.trade_df, commodity_hs, dest_m49, origin_m49,
                int(periods[-1]),
            )
            if "error" not in dep_result:
                dependency = dep_result

    # Section 5 (trade anomalies) -- compute from trade data
    trade_flow = None
    if state.trade_df is not None and not state.trade_df.empty:
        periods = sorted(state.trade_df["period"].unique())
        if periods:
            period = int(periods[-1])
            uv_df = compute_unit_value_anomalies(
                state.trade_df, commodity_hs, dest_m49, period
            )
            z_uv = float("nan")
            unit_value = float("nan")
            peers = []
            if not uv_df.empty:
                row = uv_df[uv_df["partnerCode"].astype(int) == origin_m49]
                if not row.empty:
                    z_uv = float(row.iloc[0]["z_uv"])
                    unit_value = float(row.iloc[0]["unit_value"])
                peers = [
                    {"partnerCode": int(r["partnerCode"]), "unit_value": float(r["unit_value"]), "z_uv": float(r["z_uv"])}
                    for _, r in uv_df.iterrows()
                ]

            mtd = compute_mirror_discrepancy(
                state.trade_df, commodity_hs, dest_m49, origin_m49, period
            )

            delta_hhi = None
            if len(periods) >= 2:
                shifts = compute_concentration_shifts(
                    state.trade_df, commodity_hs, dest_m49,
                    int(periods[-1]), int(periods[-2]),
                )
                delta_hhi = shifts.get("delta_hhi")

            trade_flow = {
                "unit_value": unit_value,
                "z_uv": z_uv,
                "mtd": mtd,
                "delta_hhi": delta_hhi,
                "peer_unit_values": peers,
            }

    return {
        "commodity_hs": commodity_hs,
        "commodity_name": base.get("commodity_name", ""),
        "destination_m49": dest_m49,
        "destination_country": base.get("destination_country", ""),
        "origin_m49": origin_m49,
        "origin_country": base.get("origin_country", ""),
        "destination_roles": base.get("destination_roles", []),
        "role_counts": base.get("role_counts", {}),
        "is_active_destination": base.get("is_active_destination", False),
        "dependency": dependency,
        "hazard": hazard,
        "trade_flow": trade_flow,
        "cvs": base.get("cvs"),
        "cvs_hazard_only": base.get("cvs_hazard_only"),
        "cvs_missing_inputs": base.get("cvs_missing_inputs", []),
        "sci_norm": base.get("sci_norm"),
        "his_norm": base.get("his_norm"),
        "crs_norm": base.get("crs_norm"),
    }


@router.get("/{commodity_hs}/{dest_m49}/{origin_m49}/trade-anomalies")
def get_trade_anomalies(
    commodity_hs: str,
    dest_m49: int,
    origin_m49: int,
    state: AppState = Depends(get_state),
):
    """Section 5 trade flow anomaly metrics."""
    if state.trade_df is None or state.trade_df.empty:
        return {"error": "No trade data available"}

    periods = sorted(state.trade_df["period"].unique())
    if not periods:
        return {"error": "No periods in trade data"}
    period = int(periods[-1])

    uv_df = compute_unit_value_anomalies(
        state.trade_df, commodity_hs, dest_m49, period
    )
    z_uv = float("nan")
    unit_value = float("nan")
    peers = []
    if not uv_df.empty:
        row = uv_df[uv_df["partnerCode"].astype(int) == origin_m49]
        if not row.empty:
            z_uv = float(row.iloc[0]["z_uv"])
            unit_value = float(row.iloc[0]["unit_value"])
        peers = [
            {"partnerCode": int(r["partnerCode"]), "unit_value": float(r["unit_value"]), "z_uv": float(r["z_uv"])}
            for _, r in uv_df.iterrows()
        ]

    mtd = compute_mirror_discrepancy(
        state.trade_df, commodity_hs, dest_m49, origin_m49, period
    )

    delta_hhi = None
    if len(periods) >= 2:
        shifts = compute_concentration_shifts(
            state.trade_df, commodity_hs, dest_m49,
            int(periods[-1]), int(periods[-2]),
        )
        delta_hhi = shifts.get("delta_hhi")

    return {
        "unit_value": unit_value,
        "z_uv": z_uv,
        "mtd": mtd,
        "delta_hhi": delta_hhi,
        "peer_unit_values": peers,
    }


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
