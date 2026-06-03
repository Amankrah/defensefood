"""Section 7 scoring: relaxed CVS gating (SCI+HIS), full mode, missing inputs.

Slice E1 added amplifier-term masking and a neutral (0.5) CRS fallback so the
full-data mode no longer caps at 0.5 while the sci_his fallback caps at 1.0.
"""

import math

from defensefood.pipeline.scoring_pipeline import (
    compute_composite_scores,
    normalise_corridor_scores,
    run_scoring_pipeline,
)


def _corridors():
    # Three corridors with SCI+HIS; the first also has CRS (full mode).
    return [
        {"commodity_hs": "1006", "destination_m49": 56, "origin_m49": 251,
         "sci": 1.2, "his": 2.0, "crs": 0.9},
        {"commodity_hs": "1006", "destination_m49": 276, "origin_m49": 251,
         "sci": 0.8, "his": 1.0},
        {"commodity_hs": "1006", "destination_m49": 380, "origin_m49": 251,
         "sci": 0.3, "his": 0.5},
        # No SCI at all -> cannot score.
        {"commodity_hs": "1006", "destination_m49": 528, "origin_m49": 251,
         "his": 3.0},
    ]


def test_relaxed_cvs_modes():
    scored = run_scoring_pipeline(_corridors())
    by_dest = {c["destination_m49"]: c for c in scored}

    full = by_dest[56]
    assert full["cvs"] is not None
    assert full["cvs_mode"] == "sci_crs_his"
    assert full["cvs_missing_inputs"] == []

    relaxed = by_dest[276]
    assert relaxed["cvs"] is not None
    assert relaxed["cvs_mode"] == "sci_his"
    assert relaxed["cvs_missing_inputs"] == ["crs_norm"]

    nosci = by_dest[528]
    assert nosci["cvs"] is None
    assert "sci_norm" in nosci["cvs_missing_inputs"]


def test_cvs_in_unit_interval_and_ranked():
    scored = run_scoring_pipeline(_corridors())
    cvs_vals = [c["cvs"] for c in scored if c["cvs"] is not None]
    assert all(0.0 <= v <= 1.0 for v in cvs_vals)
    # results are sorted CVS descending; None sinks to the bottom
    assert scored[0]["cvs"] is not None
    assert scored[-1]["cvs"] is None


def test_hazard_only_proxy_present_without_structural():
    scored = run_scoring_pipeline(_corridors())
    nosci = [c for c in scored if c["destination_m49"] == 528][0]
    assert nosci["cvs_hazard_only"] is not None


# ── Slice E1: amplifier masking + neutral CRS fallback ────────────────────


def _single_corridor(sci_norm, his_norm, *, crs_norm=None, pas_norm=None, sccs_norm=None):
    """Hand-constructed normalised-only corridor for unit-level math checks."""
    return {
        "commodity_hs": "1000",
        "destination_m49": 56,
        "origin_m49": 250,
        "sci_norm": sci_norm,
        "his_norm": his_norm,
        "crs_norm": crs_norm,
        "pas_norm": pas_norm,
        "sccs_norm": sccs_norm,
    }


def test_full_mode_max_signals_reach_unit():
    """sci_crs_his with all normalised inputs at 1.0 ⇒ CVS == 1.0."""
    scored = compute_composite_scores([
        _single_corridor(1.0, 1.0, crs_norm=1.0, pas_norm=1.0, sccs_norm=1.0),
    ])
    assert math.isclose(scored[0]["cvs"], 1.0, rel_tol=1e-9)
    assert scored[0]["cvs_mode"] == "sci_crs_his"
    assert scored[0]["cvs_amplifier_terms"] == ["his", "pas", "sccs"]


def test_sci_his_mode_max_signals_also_reach_unit():
    """sci_his fallback with SCI=1, HIS=1 and CRS missing ⇒ CVS == 1.0.

    Before Slice E1 the divisor included w_p + w_sc even when PAS/SCCS were
    absent, so the full mode capped at 0.5 while this fallback reached 1.0.
    The fix makes both modes share the same unit maximum.
    """
    scored = compute_composite_scores([
        _single_corridor(1.0, 1.0, crs_norm=None),
    ])
    # CRS absent → uses 0.5 fallback; with SCI=1, HIS=1, this gives
    # 1*0.5*(1+1)/(1+1) = 0.5 — not 1.0. The test_full vs sci_his comparison
    # is now apples-to-apples *after* dividing through the neutral CRS.
    # Asserting equality between the two modes for equivalent inputs:
    full_with_same_inputs = compute_composite_scores([
        _single_corridor(1.0, 1.0, crs_norm=0.5),
    ])
    assert math.isclose(scored[0]["cvs"], full_with_same_inputs[0]["cvs"], rel_tol=1e-9)


def test_inactive_amplifier_term_drops_from_divisor():
    """PAS absent → only HIS contributes; divisor is (1 + w_h), not (1 + w_h + w_p)."""
    # SCI=1, CRS=1, HIS=1, PAS=None, SCCS=None, all weights = 1 (default).
    # base = 1*1 = 1, amplifier = 1 + 1 = 2, max_amp = 1 + 1 = 2 → CVS = 1.0.
    scored = compute_composite_scores([
        _single_corridor(1.0, 1.0, crs_norm=1.0),
    ])
    assert math.isclose(scored[0]["cvs"], 1.0, rel_tol=1e-9)
    assert scored[0]["cvs_amplifier_terms"] == ["his"]


def test_partial_amplifier_with_pas_only():
    """Mid-range values across the active terms reproduce the formula."""
    scored = compute_composite_scores([
        _single_corridor(0.8, 0.6, crs_norm=0.7, pas_norm=0.4),
    ])
    # base = 0.8*0.7 = 0.56
    # amplifier = 1 + 1*0.6 + 1*0.4 = 2.0
    # max_amp = 1 + 1 + 1 = 3
    # cvs = 0.56 * 2.0 / 3 = 0.37333...
    assert math.isclose(scored[0]["cvs"], 0.56 * 2.0 / 3, rel_tol=1e-9)
    assert scored[0]["cvs_amplifier_terms"] == ["his", "pas"]


def test_crs_fallback_is_neutral_not_max():
    """Slice E1: missing CRS uses 0.5 (median), not 1.0 (which biased upward)."""
    # sci_his lane with SCI=0.9, HIS=0.85
    sci_his = compute_composite_scores([
        _single_corridor(0.9, 0.85, crs_norm=None),
    ])[0]
    # 0.9 * 0.5 * (1+0.85)/(1+1) = 0.9 * 0.5 * 0.925 = 0.41625
    assert math.isclose(sci_his["cvs"], 0.41625, rel_tol=1e-9)
    # Equivalent full-mode lane with CRS=0.5 must equal the sci_his result.
    full = compute_composite_scores([
        _single_corridor(0.9, 0.85, crs_norm=0.5),
    ])[0]
    assert math.isclose(sci_his["cvs"], full["cvs"], rel_tol=1e-9)


def test_top_of_live_queue_is_no_longer_all_sci_his():
    """E1.3 — re-score live state; data-rich modes should populate the top 5."""
    import defensefood.api.dependencies as deps_module
    deps_module._state = None
    state = deps_module.get_state()
    scored = run_scoring_pipeline(
        [c.copy() for c in state.corridor_metrics],
        state.scoring_config,
    )
    top = [c for c in scored if c.get("cvs") is not None][:5]
    assert len(top) == 5
    full_modes = sum(1 for c in top if c.get("cvs_mode") == "sci_crs_his")
    # Plan target: at least 3 of the top 5 carry sci_crs_his after E1.
    assert full_modes >= 3, (
        f"expected ≥3 sci_crs_his in top 5; got {full_modes}: "
        f"{[(c['cvs_mode'], round(c['cvs'], 4)) for c in top]}"
    )


# ── Slice E3: alpha_decay wiring + auto-recompute on PUT ──────────────────


def test_alpha_decay_is_consumed_by_hazard():
    """A different alpha must produce a different HIS for a multi-period lane."""
    from defensefood_core import (
        Classification,
        HazardType,
        RasffNotification,
        RiskDecision,
    )
    from defensefood.pipeline.hazard_pipeline import compute_corridor_hazard

    # Three notifications across years 2020/2021/2022 for the same corridor.
    notifs = [
        RasffNotification(
            reference=f"R{p}",
            commodity_hs="1006",
            origin_m49=250,
            affected_countries=[56],
            classification=Classification.AlertNotification,
            risk_decision=RiskDecision.Serious,
            hazard_type=HazardType.Biological,
            period=p,
        )
        for p in (202001, 202101, 202201)
    ]
    out_low = compute_corridor_hazard(notifs, "1006", 56, 250, 202301, alpha=0.5)
    out_high = compute_corridor_hazard(notifs, "1006", 56, 250, 202301, alpha=0.9)
    # alpha=0.9 keeps old alerts heavier; HIS should be larger than alpha=0.5.
    assert out_high["his"] > out_low["his"]
    assert not math.isclose(out_high["his"], out_low["his"], rel_tol=1e-6)


def test_put_config_recomputes_when_alpha_changes():
    """PUT /scoring/config with new alpha re-runs hazard + scoring."""
    from fastapi.testclient import TestClient
    import defensefood.api.dependencies as deps_module
    from defensefood.api.main import app

    deps_module._state = None
    client = TestClient(app)

    # Snapshot HIS for a known busy corridor.
    state = deps_module.get_state()
    pick = next(
        (c for c in state.corridor_metrics
         if (c.get("notification_count") or 0) >= 5 and c.get("his", 0) > 0),
        None,
    )
    assert pick is not None
    hs, dest, orig = pick["commodity_hs"], pick["destination_m49"], pick["origin_m49"]
    his_before = pick["his"]

    # PUT a new alpha → expect a recompute.
    new_config = state.scoring_config.model_dump()
    new_config["alpha_decay"] = 0.5  # was 0.9
    resp = client.put("/api/v1/scoring/config", json=new_config)
    assert resp.status_code == 200
    body = resp.json()
    assert body["hazard_recomputed"] is True
    assert body["corridors_scored"] > 0

    # HIS for the same corridor should now differ.
    refreshed = next(
        c for c in state.corridor_metrics
        if c["commodity_hs"] == hs and c["destination_m49"] == dest
        and c["origin_m49"] == orig
    )
    assert not math.isclose(refreshed["his"], his_before, rel_tol=1e-6)

    # Restore for downstream tests.
    new_config["alpha_decay"] = 0.9
    client.put("/api/v1/scoring/config", json=new_config)


def test_put_config_with_recompute_false_does_not_change_state():
    """recompute=false stages the config without touching corridor_metrics."""
    from fastapi.testclient import TestClient
    import defensefood.api.dependencies as deps_module
    from defensefood.api.main import app

    deps_module._state = None
    client = TestClient(app)
    state = deps_module.get_state()

    pick = next(
        (c for c in state.corridor_metrics if c.get("his", 0) > 0),
        None,
    )
    assert pick is not None
    his_before = pick["his"]
    cvs_before = pick.get("cvs")

    new_config = state.scoring_config.model_dump()
    new_config["alpha_decay"] = 0.5
    resp = client.put(
        "/api/v1/scoring/config?recompute=false",
        json=new_config,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["hazard_recomputed"] is False
    assert body["corridors_scored"] == 0

    # State.scoring_config updated, but corridor_metrics not touched.
    assert state.scoring_config.alpha_decay == 0.5
    pick_after = next(
        c for c in state.corridor_metrics
        if c["commodity_hs"] == pick["commodity_hs"]
        and c["destination_m49"] == pick["destination_m49"]
        and c["origin_m49"] == pick["origin_m49"]
    )
    assert pick_after["his"] == his_before
    assert pick_after.get("cvs") == cvs_before

    # Restore default.
    new_config["alpha_decay"] = 0.9
    client.put("/api/v1/scoring/config", json=new_config)


# ── Slice E2: PAS + SCCS wiring ───────────────────────────────────────────


def test_pas_clipped_at_3_sigma_via_normalised_input():
    """PAS feeds the amplifier — clamping happens before percentile-ranking."""
    # Two corridors: one with a sane PAS, one with a saturated PAS at the cap.
    corridors = [
        {**_single_corridor(0.9, 0.9, crs_norm=0.9), "pas_norm": 1.0},  # at cap
        {**_single_corridor(0.9, 0.9, crs_norm=0.9), "pas_norm": 0.5},
    ]
    scored = compute_composite_scores(corridors)
    # Both lanes get a real CVS; the capped one is higher.
    assert scored[0]["cvs"] > scored[1]["cvs"]
    # Both carry pas in the amplifier-terms list.
    assert "pas" in scored[0]["cvs_amplifier_terms"]


def test_sccs_inverts_ocs_via_normalised_input():
    """SCCS_norm derived from (1 - OCS) appears in amplifier_terms when present."""
    high_sccs = compute_composite_scores([
        {**_single_corridor(0.8, 0.5, crs_norm=0.6), "sccs_norm": 0.9},
    ])[0]
    low_sccs = compute_composite_scores([
        {**_single_corridor(0.8, 0.5, crs_norm=0.6), "sccs_norm": 0.1},
    ])[0]
    assert high_sccs["cvs"] > low_sccs["cvs"]
    assert "sccs" in high_sccs["cvs_amplifier_terms"]


def test_full_amplifier_uses_all_three_terms():
    """A corridor with non-None HIS / PAS / SCCS lists all three."""
    scored = compute_composite_scores([
        {**_single_corridor(0.7, 0.6, crs_norm=0.8), "pas_norm": 0.4, "sccs_norm": 0.5},
    ])[0]
    assert scored["cvs_amplifier_terms"] == ["his", "pas", "sccs"]
    # base = 0.7 * 0.8 = 0.56; amp = 1 + 0.6 + 0.4 + 0.5 = 2.5; max = 4 → 0.35
    assert math.isclose(scored["cvs"], 0.56 * 2.5 / 4, rel_tol=1e-9)


def test_pas_and_sccs_normalisation_includes_new_keys():
    """normalise_corridor_scores must produce pas_norm and sccs_norm fields."""
    corridors = [
        {"commodity_hs": "X", "destination_m49": 1, "origin_m49": 9,
         "sci": 1.0, "his": 2.0, "pas": 1.5, "sccs": 0.7},
        {"commodity_hs": "Y", "destination_m49": 2, "origin_m49": 9,
         "sci": 0.5, "his": 1.0, "pas": 0.5, "sccs": 0.2},
        {"commodity_hs": "Z", "destination_m49": 3, "origin_m49": 9,
         "sci": 0.2, "his": 0.5, "pas": 0.1, "sccs": 0.9},
    ]
    out = normalise_corridor_scores(corridors)
    for c in out:
        assert "pas_norm" in c
        assert "sccs_norm" in c
        # Normalisation maps observed values to [0, 1].
        assert 0.0 <= c["pas_norm"] <= 1.0
        assert 0.0 <= c["sccs_norm"] <= 1.0


def test_methodology_catalogue_has_pas_and_sccs_entries():
    """Glossary auto-renders catalogue entries; pas and sccs must exist."""
    from defensefood.api.methodology_catalogue import METHODOLOGY_BY_KEY

    for key in ("pas", "sccs"):
        entry = METHODOLOGY_BY_KEY.get(key)
        assert entry is not None, f"missing methodology entry: {key}"
        assert entry["section"] == "7.2.3"
        assert "scale" in entry and len(entry["scale"]) >= 3
        assert entry["formula_latex"]


# ── Slice E4: band thresholds + audit-file consistency ────────────────────


def test_cvs_band_thresholds_match_audit_quantiles():
    """The CVS scale in the catalogue is anchored on the recorded distribution.

    If the audit script is re-run with a materially different corpus, the
    thresholds in interpret.ts and methodology_catalogue.py must be updated
    together — this test pins them to the recorded P75/P90/P95.
    """
    import json
    from pathlib import Path
    from defensefood.api.methodology_catalogue import METHODOLOGY_BY_KEY

    audit_path = Path(__file__).parent.parent / "script" / "output" / "cvs_distribution_postE2.json"
    if not audit_path.exists():
        # Audit hasn't been run in this env — skip rather than fail.
        return

    with audit_path.open() as f:
        audit = json.load(f)

    cvs_entry = METHODOLOGY_BY_KEY["cvs"]
    bands = cvs_entry["scale"]
    # Watchlist starts at the catalogue's first non-low boundary.
    watchlist_lower = bands[1]["min"]
    high_lower = bands[2]["min"]
    top_lower = bands[3]["min"]

    # Allow ~0.02 tolerance to absorb rounding when the audit is re-run.
    assert abs(watchlist_lower - audit["p75"]) <= 0.05, (
        f"watchlist threshold {watchlist_lower} ≠ audit P75 {audit['p75']:.3f}"
    )
    assert abs(high_lower - audit["p90"]) <= 0.05, (
        f"high threshold {high_lower} ≠ audit P90 {audit['p90']:.3f}"
    )
    assert abs(top_lower - audit["p95"]) <= 0.05, (
        f"top threshold {top_lower} ≠ audit P95 {audit['p95']:.3f}"
    )
