"""Network graph endpoints."""

from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, Query

from defensefood.api.dependencies import AppState, get_state
from defensefood.ingestion.countries import get_country_name, is_eu27
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


@router.get("/graph")
def get_network_graph(
    commodity: Optional[str] = Query(None, description="Filter edges by HS code"),
    state: AppState = Depends(get_state),
):
    """Serialised exposure network for frontend visualisation."""
    corridors = state.corridor_metrics
    if commodity:
        corridors = [c for c in corridors if c.get("commodity_hs") == commodity]

    # Build nodes from corridor data
    node_map: dict[int, dict] = {}
    for c in corridors:
        for role, m49_key, name_key in [
            ("origin", "origin_m49", "origin_country"),
            ("dest", "destination_m49", "destination_country"),
        ]:
            m49 = c.get(m49_key, 0)
            if m49 not in node_map:
                node_map[m49] = {
                    "m49": m49,
                    "name": c.get(name_key, "") or get_country_name(m49) or str(m49),
                    "is_eu27": is_eu27(m49),
                    "corridor_count": 0,
                    "total_his": 0.0,
                }
            node_map[m49]["corridor_count"] += 1
            node_map[m49]["total_his"] += c.get("his", 0.0)

    # Build edges
    edges = []
    for c in corridors:
        edges.append({
            "origin_m49": c.get("origin_m49", 0),
            "destination_m49": c.get("destination_m49", 0),
            "commodity_hs": c.get("commodity_hs", ""),
            "his": c.get("his", 0.0),
            "severity_total": c.get("severity_total", 0.0),
        })

    nodes = list(node_map.values())
    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


@router.get("/origins")
def get_origin_risk(
    limit: int = Query(20, ge=1, le=100),
    state: AppState = Depends(get_state),
):
    """Get origins ranked by total hazard output."""
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
