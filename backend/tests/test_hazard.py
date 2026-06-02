"""Section 4 hazard signal modelling — pipeline-level checks for DGI wiring."""

import math

from defensefood_core import (
    Classification,
    HazardType,
    RasffNotification,
    RiskDecision,
)
from defensefood.pipeline.hazard_pipeline import compute_dgi_for_corridor


# ── Builders ──────────────────────────────────────────────────────────────


def _notif(
    *,
    reference: str,
    commodity_hs: str,
    origin_m49: int,
    affected: list[int],
    period: int = 202612,
    classification: Classification = Classification.AlertNotification,
    risk_decision: RiskDecision = RiskDecision.Serious,
    hazard_type: HazardType = HazardType.Biological,
) -> RasffNotification:
    return RasffNotification(
        reference=reference,
        commodity_hs=commodity_hs,
        origin_m49=origin_m49,
        affected_countries=affected,
        classification=classification,
        risk_decision=risk_decision,
        hazard_type=hazard_type,
        period=period,
    )


# ── DGI behaviour ─────────────────────────────────────────────────────────


def test_dgi_under_inspected_when_trade_share_exceeds_notification_share():
    """Lane carries 60% of trade but only 20% of notifications -> DGI ~ +0.4."""
    # Five notifications hitting Belgium imports of HS 1006:
    # Origin France contributes 1; the other 4 come from a different origin.
    other_origin = 276  # Germany — not the lane we measure
    notifications = [
        _notif(reference="2026.0001", commodity_hs="1006",
               origin_m49=251, affected=[56]),  # France→Belgium
        _notif(reference="2026.0002", commodity_hs="1006",
               origin_m49=other_origin, affected=[56]),
        _notif(reference="2026.0003", commodity_hs="1006",
               origin_m49=other_origin, affected=[56]),
        _notif(reference="2026.0004", commodity_hs="1006",
               origin_m49=other_origin, affected=[56]),
        _notif(reference="2026.0005", commodity_hs="1006",
               origin_m49=other_origin, affected=[56]),
    ]
    dgi = compute_dgi_for_corridor(
        notifications,
        commodity_hs="1006",
        destination_m49=56,
        origin_m49=251,
        bilateral_import_kg=60_000.0,   # France->Belgium = 60%
        total_import_kg=100_000.0,
    )
    # trade_share = 0.6, notification_share = 1/5 = 0.2 -> DGI = 0.4
    assert math.isclose(dgi, 0.4, abs_tol=1e-9)


def test_dgi_over_represented_when_notification_share_exceeds_trade_share():
    """Lane carries 20% of trade but generates 80% of notifications -> DGI ~ -0.6."""
    other_origin = 276
    notifications = [
        _notif(reference="r1", commodity_hs="1006", origin_m49=251, affected=[56]),
        _notif(reference="r2", commodity_hs="1006", origin_m49=251, affected=[56]),
        _notif(reference="r3", commodity_hs="1006", origin_m49=251, affected=[56]),
        _notif(reference="r4", commodity_hs="1006", origin_m49=251, affected=[56]),
        _notif(reference="r5", commodity_hs="1006", origin_m49=other_origin, affected=[56]),
    ]
    dgi = compute_dgi_for_corridor(
        notifications,
        commodity_hs="1006",
        destination_m49=56,
        origin_m49=251,
        bilateral_import_kg=20_000.0,
        total_import_kg=100_000.0,
    )
    # trade_share = 0.2, notification_share = 4/5 = 0.8 -> DGI = -0.6
    assert math.isclose(dgi, -0.6, abs_tol=1e-9)


def test_dgi_returns_nan_when_no_notifications_match():
    """No notifications for the destination -> engine returns NaN."""
    dgi = compute_dgi_for_corridor(
        notifications=[],
        commodity_hs="1006",
        destination_m49=56,
        origin_m49=251,
        bilateral_import_kg=10_000.0,
        total_import_kg=50_000.0,
    )
    assert math.isnan(dgi)


def test_dgi_returns_nan_when_no_trade_volume():
    """Total imports = 0 -> ratio undefined; engine returns NaN."""
    notifications = [
        _notif(reference="r1", commodity_hs="1006", origin_m49=251, affected=[56]),
    ]
    dgi = compute_dgi_for_corridor(
        notifications,
        commodity_hs="1006",
        destination_m49=56,
        origin_m49=251,
        bilateral_import_kg=0.0,
        total_import_kg=0.0,
    )
    assert math.isnan(dgi)


def test_dgi_aligned_when_trade_and_notifications_match():
    """Trade share equal to notification share -> DGI ~ 0."""
    notifications = [
        _notif(reference="r1", commodity_hs="1006", origin_m49=251, affected=[56]),
        _notif(reference="r2", commodity_hs="1006", origin_m49=276, affected=[56]),
    ]
    dgi = compute_dgi_for_corridor(
        notifications,
        commodity_hs="1006",
        destination_m49=56,
        origin_m49=251,
        bilateral_import_kg=50_000.0,    # 50% of trade
        total_import_kg=100_000.0,
    )
    # trade_share = 0.5, notification_share = 1/2 = 0.5 -> DGI = 0
    assert math.isclose(dgi, 0.0, abs_tol=1e-9)


def test_dgi_only_counts_notifications_for_target_destination():
    """Notifications affecting other destinations don't contribute."""
    other_dest = 380  # not in scope
    notifications = [
        _notif(reference="r1", commodity_hs="1006", origin_m49=251, affected=[56]),
        # The next three affect a DIFFERENT destination — should not influence DGI for dest=56.
        _notif(reference="r2", commodity_hs="1006", origin_m49=276, affected=[other_dest]),
        _notif(reference="r3", commodity_hs="1006", origin_m49=276, affected=[other_dest]),
        _notif(reference="r4", commodity_hs="1006", origin_m49=276, affected=[other_dest]),
    ]
    dgi = compute_dgi_for_corridor(
        notifications,
        commodity_hs="1006",
        destination_m49=56,
        origin_m49=251,
        bilateral_import_kg=40_000.0,
        total_import_kg=100_000.0,
    )
    # Only the first notification touches dest=56, so notification_share for
    # France->Belgium = 1/1 = 1.0, trade_share = 0.4 -> DGI = -0.6
    assert math.isclose(dgi, -0.6, abs_tol=1e-9)


# ── Methodology catalogue consistency ─────────────────────────────────────


def test_methodology_dgi_entry_is_correct():
    """DGI entry in the catalogue must match the engine semantics
    (subtraction, not ratio) and be in Section 4.5."""
    from defensefood.api.methodology_catalogue import METHODOLOGY_BY_KEY
    entry = METHODOLOGY_BY_KEY["dgi"]
    assert entry["section"] == "4.5"
    assert "M(c,i,j,t)" in entry["formula_latex"] and "R(c,i,j,t)" in entry["formula_latex"]
    # subtraction, not division
    assert "-" in entry["formula_latex"]
    # Scale must span the negative range too (subtraction can be < 0).
    band_mins = [b["min"] for b in entry["scale"]]
    assert min(band_mins) < 0
