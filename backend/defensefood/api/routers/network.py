"""Network graph endpoints."""

from fastapi import APIRouter, Depends, Query

from defensefood.api.dependencies import AppState, get_state
from defensefood.pipeline.network_pipeline import build_exposure_network

router = APIRouter(prefix="/network", tags=["network"])


@router.get("/summary")
def get_network_summary(state: AppState = Depends(get_state)):
    """Get summary of the exposure network."""
    net = build_exposure_network(state.corridor_metrics)
    return {
        "node_count": net.node_count,
        "edge_count": net.edge_count,
    }


@router.get("/origins")
def get_origin_risk(
    limit: int = Query(20, ge=1, le=100),
    state: AppState = Depends(get_state),
):
    """Get origins ranked by total hazard output."""
    from collections import defaultdict

    origin_stats: dict[int, dict] = defaultdict(lambda: {
        "total_his": 0.0,
        "total_severity": 0.0,
        "corridor_count": 0,
        "name": "",
    })

    for c in state.corridor_metrics:
        origin = c.get("origin_m49", 0)
        origin_stats[origin]["total_his"] += c.get("his", 0.0)
        origin_stats[origin]["total_severity"] += c.get("severity_total", 0.0)
        origin_stats[origin]["corridor_count"] += 1
        origin_stats[origin]["name"] = c.get("origin_country", "")

    results = [
        {"origin_m49": m49, **stats}
        for m49, stats in origin_stats.items()
    ]
    results.sort(key=lambda x: x["total_his"], reverse=True)

    return {"count": len(results), "origins": results[:limit]}
