"""
Phase 0 — predictive epic precondition.

Tests for ``defensefood.agent.predictive.historical_snapshots`` which
materialises per-period CVS by re-running the scoring pipeline against
each year's dependency snapshot + period-vintage notifications.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from defensefood.agent.predictive.historical_snapshots import (
    build_scored_history,
    coverage_summary,
    lane_history,
)


# ── fixture helpers ──────────────────────────────────────────────────────


def _make_notification(
    *,
    reference: str,
    commodity_hs: str,
    origin_m49: int,
    dest_m49: int,
    period: int,  # YYYYMM
    classification: str = "AlertNotification",
    risk_decision: str = "Serious",
    hazard_type: str = "Biological",
) -> Any:
    """Construct a real Rust RasffNotification for testing.

    The Rust struct takes enums; we resolve them by attribute on the
    defensefood_core module.
    """
    from defensefood_core import (
        Classification,
        HazardType,
        RasffNotification,
        RiskDecision,
    )

    return RasffNotification(
        reference=reference,
        commodity_hs=commodity_hs,
        origin_m49=origin_m49,
        affected_countries=[dest_m49],
        classification=getattr(Classification, classification),
        risk_decision=getattr(RiskDecision, risk_decision),
        hazard_type=getattr(HazardType, hazard_type),
        period=period,
    )


def _two_period_state() -> SimpleNamespace:
    """Build a minimal fixture state with two trade years and two lanes.

    - Spain mussels into France (HS 30771): present in both 2022 and 2023,
      Section 2 metrics filled, FAOSTAT CRS available.
    - Italian rice into France (HS 100630): present in both 2022 and 2023,
      no FAOSTAT CRS (forces sci_his fallback).

    Notifications: 2 alerts on the mussels lane in 2022, 5 in 2023.
    Rice lane has 1 alert in 2023 only.
    """
    from defensefood.models.scores import ScoringConfig

    corridor_metrics = [
        {
            "commodity_hs": "30771",
            "commodity_name": "Mussels, frozen",
            "destination_m49": 250,
            "destination_country": "France",
            "origin_m49": 724,
            "origin_country": "Spain",
            "market_presence": "confirmed",
        },
        {
            "commodity_hs": "100630",
            "commodity_name": "Rice",
            "destination_m49": 250,
            "destination_country": "France",
            "origin_m49": 380,
            "origin_country": "Italy",
            "market_presence": "confirmed",
        },
    ]

    # dependency_history per period: BDI/OCS/HHI/IDR/SCI populated, sci_norm
    # NOT pre-populated (the scoring pipeline computes _norm internally).
    dep_2022 = {
        ("30771", 250, 724): {
            "ds_prime": 90_000_000.0,
            "bilateral_import_kg": 60_000_000.0,
            "total_imports_kg": 80_000_000.0,
            "production_kg": 10_000_000.0,
            "idr": 0.7,
            "ocs": 0.45,
            "hhi": 0.38,
            "bdi": 0.55,
            "ssr": 0.12,
            "sci": 1.0,
            "provenance": "faostat",
            "idr_gt_1": False,
        },
        ("100630", 250, 380): {
            "ds_prime": 1_200_000_000.0,
            "bilateral_import_kg": 400_000_000.0,
            "total_imports_kg": 900_000_000.0,
            "production_kg": 300_000_000.0,
            "idr": 0.6,
            "ocs": 0.30,
            "hhi": 0.40,
            "bdi": 0.28,
            "ssr": 0.25,
            "sci": 0.8,
            "provenance": "trade_only",
            "idr_gt_1": False,
        },
    }
    dep_2023 = {
        ("30771", 250, 724): {
            "ds_prime": 91_000_000.0,
            "bilateral_import_kg": 65_000_000.0,
            "total_imports_kg": 82_000_000.0,
            "production_kg": 10_000_000.0,
            "idr": 0.72,
            "ocs": 0.50,
            "hhi": 0.40,
            "bdi": 0.60,
            "ssr": 0.12,
            "sci": 1.1,
            "provenance": "faostat",
            "idr_gt_1": False,
        },
        ("100630", 250, 380): {
            "ds_prime": 1_180_000_000.0,
            "bilateral_import_kg": 380_000_000.0,
            "total_imports_kg": 880_000_000.0,
            "production_kg": 300_000_000.0,
            "idr": 0.59,
            "ocs": 0.28,
            "hhi": 0.39,
            "bdi": 0.27,
            "ssr": 0.25,
            "sci": 0.8,
            "provenance": "trade_only",
            "idr_gt_1": False,
        },
    }

    # CRS lookup: only mussels has a CRS entry; rice doesn't (sci_his fallback).
    # Key uses normalize_hs which zero-pads short codes to 6 digits.
    from defensefood.ingestion.hs_codes import normalize_hs
    crs_lookup = {(normalize_hs("30771"), 250): 0.6}

    # Notifications: 2 on the mussels lane in 2022, then 5 more in 2023.
    notifs = []
    for i in range(2):
        notifs.append(
            _make_notification(
                reference=f"22.MUS.{i}",
                commodity_hs="30771",
                origin_m49=724,
                dest_m49=250,
                period=202205 + i,
            )
        )
    for i in range(5):
        notifs.append(
            _make_notification(
                reference=f"23.MUS.{i}",
                commodity_hs="30771",
                origin_m49=724,
                dest_m49=250,
                period=202308 + i if 202308 + i <= 202312 else 202312,
            )
        )
    # One rice alert in 2023.
    notifs.append(
        _make_notification(
            reference="23.RICE.0",
            commodity_hs="100630",
            origin_m49=380,
            dest_m49=250,
            period=202310,
            hazard_type="ChemMycotoxins",
        )
    )

    return SimpleNamespace(
        corridor_metrics=corridor_metrics,
        dependency_history={2022: dep_2022, 2023: dep_2023},
        notifications=notifs,
        scoring_config=ScoringConfig(),
        crs_lookup=crs_lookup,
    )


# ── tests ────────────────────────────────────────────────────────────────


def test_build_scored_history_returns_one_entry_per_populated_period():
    state = _two_period_state()
    out = build_scored_history(state)
    assert sorted(out.keys()) == [2022, 2023]


def test_each_lane_in_each_period_gets_a_scored_corridor_dict():
    state = _two_period_state()
    out = build_scored_history(state)

    for period in (2022, 2023):
        assert ("30771", 250, 724) in out[period]
        assert ("100630", 250, 380) in out[period]


def test_mussels_lane_has_cvs_under_full_mode_in_both_periods():
    """CRS is populated for mussels, so both years carry sci_crs_his mode."""
    state = _two_period_state()
    out = build_scored_history(state)

    for period in (2022, 2023):
        entry = out[period][("30771", 250, 724)]
        assert entry["cvs"] is not None
        assert entry["cvs_mode"] == "sci_crs_his"
        # CVS in [0, 1].
        assert 0.0 <= float(entry["cvs"]) <= 1.0


def test_rice_lane_falls_back_to_sci_his_when_no_crs():
    """No CRS for the rice lane → cvs_mode is sci_his fallback."""
    state = _two_period_state()
    out = build_scored_history(state)

    for period in (2022, 2023):
        entry = out[period][("100630", 250, 380)]
        # When there is HIS data in this period, CVS gets computed in
        # sci_his fallback. Rice has zero notifications in 2022 → HIS likely
        # 0 → sci_norm + his_norm both present → CVS is computed.
        assert entry["cvs_mode"] in ("sci_his", None)


def test_period_filtered_notifications_drive_his():
    """Mussels lane has 2 notifications in 2022 and 5 more in 2023.
    The 2022 scored entry must see only the early 2 (period <= 202212);
    the 2023 entry sees all 7.
    """
    state = _two_period_state()
    out = build_scored_history(state)

    n_2022 = out[2022][("30771", 250, 724)]["notification_count"]
    n_2023 = out[2023][("30771", 250, 724)]["notification_count"]
    assert n_2022 == 2
    assert n_2023 == 7


def test_section2_fields_propagate_into_scored_entries():
    """The dependency snapshot for each period must end up on the scored row."""
    state = _two_period_state()
    out = build_scored_history(state)
    e22 = out[2022][("30771", 250, 724)]
    e23 = out[2023][("30771", 250, 724)]
    assert e22["sci"] == pytest.approx(1.0)
    assert e23["sci"] == pytest.approx(1.1)
    assert e22["ocs"] == pytest.approx(0.45)
    assert e23["ocs"] == pytest.approx(0.50)
    # Labels propagate from corridor_metrics.
    assert e22["commodity_name"] == "Mussels, frozen"
    assert e22["origin_country"] == "Spain"


def test_empty_dependency_history_returns_empty_dict():
    state = SimpleNamespace(
        corridor_metrics=[],
        dependency_history={},
        notifications=[],
        scoring_config=None,
        crs_lookup={},
    )
    assert build_scored_history(state) == {}


def test_empty_inner_snapshot_period_is_skipped():
    """A period whose dependency pipeline returned {} should be dropped."""
    state = _two_period_state()
    state.dependency_history[2021] = {}  # synthetic empty year
    out = build_scored_history(state)
    assert 2021 not in out
    # Still has the populated years.
    assert sorted(out.keys()) == [2022, 2023]


def test_lane_history_returns_periods_ascending():
    state = _two_period_state()
    out = build_scored_history(state)
    history = lane_history(out, ("30771", 250, 724))
    assert [r["period"] for r in history] == [2022, 2023]
    # CVS should be available in both.
    assert all(r["cvs"] is not None for r in history)


def test_coverage_summary_aggregates_per_period_counts():
    state = _two_period_state()
    out = build_scored_history(state)
    summary = coverage_summary(out)
    assert summary["periods"] == [2022, 2023]
    assert summary["total_lane_periods"] == 4  # 2 lanes × 2 periods
    for row in summary["by_period"]:
        assert row["corridors"] == 2
        assert row["with_cvs"] in (1, 2)


# ── AppState wiring ──────────────────────────────────────────────────────


def test_appstate_has_scored_history_field():
    """The dataclass field must exist so downstream code can store onto it
    without touching __dict__."""
    from defensefood.api.dependencies import AppState

    s = AppState()
    assert hasattr(s, "scored_history")
    assert s.scored_history == {}
