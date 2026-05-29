"""Section 7 scoring: relaxed CVS gating (SCI+HIS), full mode, missing inputs."""

from defensefood.pipeline.scoring_pipeline import run_scoring_pipeline


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
