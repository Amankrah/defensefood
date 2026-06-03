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

    When ``bdi`` is missing the edge contributes ``dep_weight = 0.0`` (and
    therefore zero to ACEP/ORPS). The earlier fallback that substituted
    ``severity_total`` here was unsound — severity is a hazard quantity, not
    a dependency share — so we drop it entirely and rely on the caller to
    surface ``dep_weight_provenance == "missing"`` per lane if needed.
    """
    net = NetworkEngine()

    for c in corridors_with_metrics:
        raw_bdi = c.get("bdi")
        dep_weight = float(raw_bdi) if raw_bdi is not None else 0.0
        net.add_edge(
            origin_m49=c.get("origin_m49", 0),
            dest_m49=c.get("destination_m49", 0),
            commodity_hs=c.get("commodity_hs", ""),
            trade_weight=float(c.get("bilateral_import_kg", 0.0) or 0.0),
            hazard_weight=float(c.get("his", 0.0) or 0.0),
            dep_weight=dep_weight,
            role=c.get("market_presence"),
        )

    return net


def estimate_avg_shipment_size_by_hs_chapter(
    trade_df: pd.DataFrame,
    *,
    min_rows: int = 30,
) -> dict[str, float]:
    """Estimate average shipment size m̄(c) per HS-2 chapter (kg).

    Blueprint §6.4 Eq. (35) needs m̄(c) to convert total bilateral imports
    into an estimated shipment count. At HS-6 specificity the trade table
    doesn't have enough rows for a stable median; HS-2 chapter is the
    documented fallback.

    Each row in ``trade_df`` is treated as one shipment (Comtrade typically
    publishes one row per reporter/partner/HS/period). The median ``netWgt``
    over rows in a chapter is the estimator. Chapters with fewer than
    ``min_rows`` observations fall back to the global median.

    Returns a dict ``{"01": median_kg, ..., "global": median_kg}``. The
    ``"global"`` key is always present and used by the caller when a
    commodity's HS-2 chapter isn't in the lookup.
    """
    out: dict[str, float] = {}
    if trade_df is None or trade_df.empty or "netWgt" not in trade_df.columns:
        out["global"] = 0.0
        return out

    # Use only positive net weights (Comtrade publishes 0 / NaN for some rows).
    nw = trade_df["netWgt"]
    valid = trade_df.loc[nw.notna() & (nw > 0)].copy()
    if valid.empty:
        out["global"] = 0.0
        return out

    out["global"] = float(valid["netWgt"].median())

    if "cmdCode" not in valid.columns:
        return out

    valid["_hs2"] = valid["cmdCode"].astype(str).str.zfill(6).str[:2]
    grouped = valid.groupby("_hs2")["netWgt"]
    counts = grouped.size()
    medians = grouped.median()
    for chapter, n in counts.items():
        if n >= min_rows:
            out[str(chapter)] = float(medians.loc[chapter])
    return out


def lookup_avg_shipment_size(
    avg_lookup: dict[str, float],
    commodity_hs: str,
) -> float:
    """Resolve m̄(c) for a specific HS code using the chapter lookup.

    Falls back to ``avg_lookup["global"]`` when the HS-2 chapter isn't
    populated (rare chapters). Returns 0.0 if the lookup is empty.
    """
    if not avg_lookup:
        return 0.0
    if not commodity_hs:
        return float(avg_lookup.get("global", 0.0))
    chapter = str(commodity_hs).zfill(6)[:2]
    return float(avg_lookup.get(chapter) or avg_lookup.get("global", 0.0))


def count_missing_bdi_edges(
    corridors_with_metrics: list[dict],
    *,
    origin_m49: Optional[int] = None,
    destination_m49: Optional[int] = None,
) -> int:
    """Count corridors where BDI is missing (so dep_weight defaulted to 0).

    Callers pass either ``origin_m49`` (for ORPS scope) or ``destination_m49``
    (for ACEP scope) to slice the relevant subset; passing neither counts
    across the full corridor population.
    """
    n = 0
    for c in corridors_with_metrics:
        if origin_m49 is not None and c.get("origin_m49") != origin_m49:
            continue
        if destination_m49 is not None and c.get("destination_m49") != destination_m49:
            continue
        if c.get("bdi") is None:
            n += 1
    return n


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

    # Section 2 BDI is the only valid dependency weight; corridors without
    # BDI contribute 0 to ACEP/ORPS rather than the prior severity proxy.
    enriched = []
    for m in corridor_metrics:
        bdi = m.get("bdi")
        enriched.append({
            "commodity_hs": m.get("commodity_hs", ""),
            "destination_m49": m.get("destination_m49", 0),
            "origin_m49": m.get("origin_m49", 0),
            "bdi": bdi,
            "his": m.get("his", 0.0),
            "bilateral_import_kg": m.get("bilateral_import_kg", 0.0) or 0.0,
            "market_presence": m.get("market_presence"),
        })

    net = build_exposure_network(enriched)

    return {
        "network": net,
        "node_count": net.node_count,
        "edge_count": net.edge_count,
    }
