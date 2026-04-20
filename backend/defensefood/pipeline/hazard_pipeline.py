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
from defensefood.core import (
    HazardEngine,
    parse_classification,
    parse_hazard_type,
    parse_hazard_types,
    parse_risk_decision,
)
from defensefood.ingestion.countries import get_m49_code
from defensefood.ingestion.rasff import Corridor, extract_corridors, load_rasff_data


def build_notifications(
    corridors: list[Corridor],
) -> list[RasffNotification]:
    """Convert extracted corridors to Rust RasffNotification objects.

    The Rust struct stores a single origin per notification, so a notification
    that lists multiple origins (e.g. "France,Ireland,Netherlands") emits one
    RasffNotification per origin, each carrying the full set of affected
    destinations for that reference.

    Grouping key: (reference, origin_m49).
    """
    by_ref_origin: dict[tuple[str, int], dict] = {}
    for c in corridors:
        key = (c.reference, c.origin_m49)
        if key not in by_ref_origin:
            by_ref_origin[key] = {
                "reference": c.reference,
                "commodity_hs": c.commodity_hs,
                "origin_m49": c.origin_m49,
                "affected_countries": set(),
                "classification": c.classification,
                "risk_decision": c.risk_decision,
                "hazard_category": c.hazard_category,
                "period": c.period,
            }
        by_ref_origin[key]["affected_countries"].add(c.destination_m49)

    notifications = []
    for data in by_ref_origin.values():
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
    hazard_category_map: Optional[dict[str, str]] = None,
) -> dict:
    """Compute all Section 4 hazard metrics for a single corridor.

    Returns dict with keys: his, hdi, notification_count, severity_total,
    hazard_breakdown (per-category counts used for HDI).

    `hazard_category_map` is an optional {reference -> raw-hazards-string}
    mapping so HDI can include every category token on a notification, not
    just the single `hazard_type` enum the Rust struct can hold. When a
    notification lists "mycotoxins,pathogenic micro-organisms" we want both
    categories to contribute to the diversity index.
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
    # Slot ordering matches defensefood_core.HazardType discriminants:
    #   [Biological, ChemPesticides, ChemHeavyMetals, ChemMycotoxins, ChemOther, Regulatory]
    from defensefood_core import HazardType

    def _slot(ht: HazardType) -> int:
        if ht == HazardType.Biological: return 0
        if ht == HazardType.ChemPesticides: return 1
        if ht == HazardType.ChemHeavyMetals: return 2
        if ht == HazardType.ChemMycotoxins: return 3
        if ht == HazardType.ChemOther: return 4
        if ht == HazardType.Regulatory: return 5
        return 4

    hazard_counts = [0.0] * 6
    for n in corridor_notifs:
        # Prefer the richer multi-category parse when a map is provided.
        if hazard_category_map is not None and n.reference in hazard_category_map:
            hts = parse_hazard_types(hazard_category_map[n.reference])
        else:
            hts = [n.hazard_type]
        if not hts:
            hts = [n.hazard_type]
        # Fractional credit so a notification with 2 categories splits 0.5/0.5.
        share = 1.0 / len(hts)
        for ht in hts:
            hazard_counts[_slot(ht)] += share

    hdi = HazardEngine.compute_hdi(hazard_counts)

    # Severity total for this corridor
    severity_total = sum(
        HazardEngine.severity(n.classification, n.risk_decision)
        for n in corridor_notifs
    )

    labels = ["biological", "chem_pesticides", "chem_heavy_metals",
              "chem_mycotoxins", "chem_other", "regulatory"]
    hazard_breakdown = {label: round(count, 3) for label, count in zip(labels, hazard_counts)}

    return {
        "his": his,
        "hdi": hdi,
        "notification_count": notif_count,
        "severity_total": severity_total,
        "hazard_breakdown": hazard_breakdown,
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

    # Aggregate destination roles per corridor key across all notifications
    from defensefood.ingestion.rasff import ACTIVE_ROLES

    roles_by_corridor: dict[tuple[str, int, int], set[str]] = {}
    role_counts_by_corridor: dict[tuple[str, int, int], dict[str, int]] = {}
    for c in corridors:
        key = (c.commodity_hs, c.destination_m49, c.origin_m49)
        if key not in roles_by_corridor:
            roles_by_corridor[key] = set()
            role_counts_by_corridor[key] = {
                "notifier": 0, "distribution": 0,
                "followUp": 0, "attention": 0,
            }
        for r in c.destination_roles:
            roles_by_corridor[key].add(r)
            role_counts_by_corridor[key][r] += 1

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

        roles = roles_by_corridor.get(key, set())
        metrics["destination_roles"] = sorted(roles)
        metrics["role_counts"] = role_counts_by_corridor.get(key, {})
        metrics["is_active_destination"] = bool(roles & ACTIVE_ROLES)

        corridor_metrics.append(metrics)

    return {
        "notifications": notifications,
        "corridors": corridors,
        "summary": summary,
        "corridor_metrics": corridor_metrics,
        "current_period": current_period,
    }
