"""
Network Pipeline -- Section 6 computation orchestration.

Builds the exposure network graph from trade and hazard data,
then computes ORPS (per origin) and ACEP (per destination).
"""

from typing import Optional

import pandas as pd

from defensefood.core import (
    ConsumptionEngine,
    DependencyEngine,
    HazardEngine,
    NetworkEngine,
)
from defensefood_core import RasffNotification
from defensefood.ingestion.countries import get_country_name, is_eu27
from defensefood.models.network import GraphEdge, GraphNode, NetworkSummary


def build_exposure_network(
    corridors_with_metrics: list[dict],
) -> NetworkEngine:
    """Build the exposure network from pre-computed corridor metrics.

    Each entry in corridors_with_metrics should have:
        commodity_hs, destination_m49, origin_m49,
        bdi (dep_weight), his (hazard_weight), bilateral_import_kg (trade_weight).
    """
    net = NetworkEngine()

    for c in corridors_with_metrics:
        net.add_edge(
            origin_m49=c.get("origin_m49", 0),
            dest_m49=c.get("destination_m49", 0),
            commodity_hs=c.get("commodity_hs", ""),
            trade_weight=c.get("bilateral_import_kg", 0.0),
            hazard_weight=c.get("his", 0.0),
            dep_weight=c.get("bdi", 0.0),
        )

    return net


def compute_orps_for_origin(
    net: NetworkEngine,
    origin_m49: int,
    commodity_hs: str,
    pcc_by_country: dict[int, float],
) -> float:
    """Compute Origin Risk Propagation Score (Eq. 33) for one origin+commodity."""
    return net.compute_orps(origin_m49, commodity_hs, pcc_by_country)


def compute_acep_for_country(
    net: NetworkEngine,
    destination_m49: int,
    crs_by_commodity: dict[str, float],
) -> float:
    """Compute Attention Country Exposure Profile (Eq. 34) for one destination."""
    return net.compute_acep(destination_m49, crs_by_commodity)


def serialise_network(net: NetworkEngine) -> NetworkSummary:
    """Serialise the network for frontend visualisation."""
    # The ExposureNetwork is opaque, so we reconstruct from edge queries.
    # For now, return a summary with counts.
    return NetworkSummary(
        nodes=[],
        edges=[],
        node_count=net.node_count,
        edge_count=net.edge_count,
    )


def run_network_pipeline(
    hazard_results: dict,
    trade_df: Optional[pd.DataFrame] = None,
) -> dict:
    """Run the network pipeline using hazard pipeline output.

    Args:
        hazard_results: Output from run_hazard_pipeline().
        trade_df: Trade DataFrame (for BDI computation). Optional.

    Returns:
        Dict with 'network', 'node_count', 'edge_count'.
    """
    corridor_metrics = hazard_results.get("corridor_metrics", [])

    # Enrich corridor metrics with placeholder BDI and trade weight
    # (full BDI requires FAOSTAT production data; use hazard weight as proxy for now)
    enriched = []
    for m in corridor_metrics:
        enriched.append({
            "commodity_hs": m.get("commodity_hs", ""),
            "destination_m49": m.get("destination_m49", 0),
            "origin_m49": m.get("origin_m49", 0),
            "bdi": m.get("severity_total", 0.0),  # Proxy until FAOSTAT available
            "his": m.get("his", 0.0),
            "bilateral_import_kg": 0.0,
        })

    net = build_exposure_network(enriched)

    return {
        "network": net,
        "node_count": net.node_count,
        "edge_count": net.edge_count,
    }
