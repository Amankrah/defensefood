"""
Hazard Pipeline -- Section 4 computation orchestration.

Loads RASFF data, extracts corridors, converts to Rust notification objects,
and computes hazard signal metrics (HIS, HDI, DGI) through the Rust engine.
"""

from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import pandas as pd

from defensefood_core import RasffNotification
from defensefood.core import HazardEngine, parse_classification, parse_hazard_type, parse_risk_decision
from defensefood.ingestion.countries import get_m49_code
from defensefood.ingestion.rasff import Corridor, extract_corridors, load_rasff_data


def build_notifications(
    corridors: list[Corridor],
) -> list[RasffNotification]:
    """Convert extracted corridors to Rust RasffNotification objects.

    Groups by reference to avoid duplicating affected_countries.
    """
    # Group corridors by reference to build one notification per reference
    by_ref: dict[str, dict] = {}
    for c in corridors:
        if c.reference not in by_ref:
            by_ref[c.reference] = {
                "reference": c.reference,
                "commodity_hs": c.commodity_hs,
                "origin_m49": c.origin_m49,
                "affected_countries": set(),
                "classification": c.classification,
                "risk_decision": c.risk_decision,
                "hazard_category": c.hazard_category,
                "period": c.period,
            }
        by_ref[c.reference]["affected_countries"].add(c.destination_m49)

    notifications = []
    for data in by_ref.values():
        if not data["commodity_hs"] or not data["affected_countries"] or data["period"] == 0:
            continue
        notif = RasffNotification(
            reference=data["reference"],
            commodity_hs=data["commodity_hs"],
            origin_m49=data["origin_m49"],
            affected_countries=sorted(data["affected_countries"]),
            classification=parse_classification(data["classification"]),
            risk_decision=parse_risk_decision(data["risk_decision"]),
            hazard_type=parse_hazard_type(data["hazard_category"]),
            period=data["period"],
        )
        notifications.append(notif)

    return notifications


def compute_corridor_hazard(
    notifications: list[RasffNotification],
    commodity_hs: str,
    destination_m49: int,
    origin_m49: int,
    current_period: int,
    alpha: float = 0.90,
) -> dict:
    """Compute all Section 4 hazard metrics for a single corridor.

    Returns dict with keys: his, hdi, dgi, notification_count, severity_total.
    """
    # HIS -- Hazard Intensity Score (Eq. 15)
    his = HazardEngine.compute_his(
        notifications, commodity_hs, destination_m49, origin_m49,
        current_period, alpha,
    )

    # Count and classify notifications touching this corridor
    corridor_notifs = [
        n for n in notifications
        if n.commodity_hs == commodity_hs
        and n.origin_m49 == origin_m49
        and destination_m49 in n.affected_countries
    ]
    notif_count = len(corridor_notifs)

    # HDI -- Hazard Diversity Index (Eq. 17-18)
    # Map HazardType enum variants to indices 0-5 via string comparison
    from defensefood_core import HazardType
    hazard_counts = [0.0] * 6
    for n in corridor_notifs:
        ht = n.hazard_type
        if ht == HazardType.Biological:
            hazard_counts[0] += 1.0
        elif ht == HazardType.ChemPesticides:
            hazard_counts[1] += 1.0
        elif ht == HazardType.ChemHeavyMetals:
            hazard_counts[2] += 1.0
        elif ht == HazardType.ChemMycotoxins:
            hazard_counts[3] += 1.0
        elif ht == HazardType.ChemOther:
            hazard_counts[4] += 1.0
        elif ht == HazardType.Regulatory:
            hazard_counts[5] += 1.0
        else:
            hazard_counts[4] += 1.0
    hdi = HazardEngine.compute_hdi(hazard_counts)

    # Severity total for this corridor
    severity_total = sum(
        HazardEngine.severity(n.classification, n.risk_decision)
        for n in corridor_notifs
    )

    return {
        "his": his,
        "hdi": hdi,
        "notification_count": notif_count,
        "severity_total": severity_total,
    }


def compute_dgi_for_corridor(
    notifications: list[RasffNotification],
    commodity_hs: str,
    destination_m49: int,
    origin_m49: int,
    bilateral_import_kg: float,
    total_import_kg: float,
) -> float:
    """Compute Detection Gap Indicator (Eq. 19) for a corridor.

    Needs trade data to compute trade share alongside notification share.
    """
    # Count notifications from this origin
    bilateral_notifs = sum(
        1 for n in notifications
        if n.commodity_hs == commodity_hs
        and n.origin_m49 == origin_m49
        and destination_m49 in n.affected_countries
    )
    # Count total notifications for this commodity+destination
    total_notifs = sum(
        1 for n in notifications
        if n.commodity_hs == commodity_hs
        and destination_m49 in n.affected_countries
    )

    return HazardEngine.compute_dgi_from_counts(
        bilateral_import_kg, total_import_kg,
        float(bilateral_notifs), float(total_notifs),
    )


def run_hazard_pipeline(
    rasff_path: Optional[Path] = None,
    current_period: Optional[int] = None,
    alpha: float = 0.90,
) -> dict:
    """Run the full hazard pipeline.

    Returns:
        Dict with 'notifications', 'corridors', 'summary', and
        'corridor_metrics' (list of dicts with HIS/HDI per corridor).
    """
    df = load_rasff_data(rasff_path)
    corridors, summary = extract_corridors(df)
    notifications = build_notifications(corridors)

    if current_period is None:
        # Use the latest period from notifications
        periods = [n.period for n in notifications if n.period > 0]
        current_period = max(periods) if periods else 202600

    # Compute metrics for each unique corridor
    seen = set()
    corridor_metrics = []
    for c in corridors:
        key = (c.commodity_hs, c.destination_m49, c.origin_m49)
        if key in seen or not c.commodity_hs:
            continue
        seen.add(key)

        metrics = compute_corridor_hazard(
            notifications, c.commodity_hs, c.destination_m49, c.origin_m49,
            current_period, alpha,
        )
        metrics["commodity_hs"] = c.commodity_hs
        metrics["destination_m49"] = c.destination_m49
        metrics["origin_m49"] = c.origin_m49
        metrics["origin_country"] = c.origin_country
        metrics["destination_country"] = c.destination_country
        corridor_metrics.append(metrics)

    return {
        "notifications": notifications,
        "corridors": corridors,
        "summary": summary,
        "corridor_metrics": corridor_metrics,
        "current_period": current_period,
    }
