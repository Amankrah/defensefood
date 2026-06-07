"""
Phase 1 of the predictive epic.

Three groups of tests:

1. Feature extractor — engineered features land in ``derived`` with the
   right keys and respect causality (no future leakage).
2. Baselines — PersistenceForecaster and ChapterMedianForecaster produce
   sane predictions on a fixture state.
3. Back-test harness — ``walk_forward`` runs across multiple periods and
   the CLI ``script.predictive`` writes JSON + CSV reports.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest


# ── shared fixture: a 3-period scored history with peer lanes ───────────


def _entry(
    *,
    cvs: float | None,
    his: float = 0.3,
    sci: float = 1.0,
    ocs: float = 0.4,
    bdi: float = 0.5,
    hhi: float = 0.4,
    idr: float = 0.7,
    notif: int = 0,
    mode: str | None = "sci_crs_his",
    bilateral_kg: float = 1e6,
    period: int = 2020,
    hs: str = "30771",
    dest: int = 250,
    origin: int = 724,
    commodity_name: str = "Mussels",
    market_presence: str = "confirmed",
) -> dict[str, Any]:
    return {
        "commodity_hs": hs,
        "destination_m49": dest,
        "origin_m49": origin,
        "commodity_name": commodity_name,
        "destination_country": "France",
        "origin_country": "Spain",
        "period": period,
        "cvs": cvs,
        "cvs_mode": mode,
        "his": his,
        "sci": sci,
        "ocs": ocs,
        "bdi": bdi,
        "hhi": hhi,
        "idr": idr,
        "notification_count": notif,
        "severity_total": float(notif),
        "hdi": 0.1,
        "market_presence": market_presence,
        "provenance": "faostat",
        "idr_gt_1": False,
        "bilateral_import_kg": bilateral_kg,
    }


def _three_period_state() -> SimpleNamespace:
    """Build a fixture with three periods of scored history for two lanes
    in the same chapter × destination plus two peer lanes."""
    LANE_A = ("30771", 250, 724)  # Spain mussels into France
    LANE_B = ("30772", 250, 380)  # Italian mussels into France (peer)
    LANE_C = ("30773", 250, 528)  # Dutch mussels into France (peer)

    scored = {
        2021: {
            LANE_A: _entry(period=2021, cvs=0.30, his=0.30, notif=3),
            LANE_B: _entry(period=2021, cvs=0.25, his=0.25, notif=1,
                           hs="30772", origin=380),
            LANE_C: _entry(period=2021, cvs=0.20, his=0.20, notif=0,
                           hs="30773", origin=528),
        },
        2022: {
            LANE_A: _entry(period=2022, cvs=0.34, his=0.40, notif=5),
            LANE_B: _entry(period=2022, cvs=0.28, his=0.28, notif=2,
                           hs="30772", origin=380),
            LANE_C: _entry(period=2022, cvs=0.22, his=0.22, notif=1,
                           hs="30773", origin=528),
        },
        2023: {
            LANE_A: _entry(period=2023, cvs=0.38, his=0.45, notif=7),
            LANE_B: _entry(period=2023, cvs=0.30, his=0.30, notif=3,
                           hs="30772", origin=380),
            LANE_C: _entry(period=2023, cvs=0.25, his=0.24, notif=2,
                           hs="30773", origin=528),
        },
    }

    corridor_metrics = []
    for (hs, dest, origin), entry in scored[2023].items():
        corridor_metrics.append(
            {
                "commodity_hs": hs,
                "destination_m49": dest,
                "origin_m49": origin,
                "commodity_name": entry["commodity_name"],
                "destination_country": entry["destination_country"],
                "origin_country": entry["origin_country"],
                "market_presence": entry["market_presence"],
            }
        )
    return SimpleNamespace(
        scored_history=scored,
        corridor_metrics=corridor_metrics,
    )


# ── feature extractor ───────────────────────────────────────────────────


def test_feature_extractor_produces_base_fields():
    from defensefood.agent.predictive import extract_corridor_features

    state = _three_period_state()
    fv = extract_corridor_features(
        state, commodity_hs="30771", destination_m49=250, origin_m49=724, period=2023
    )
    assert fv is not None
    assert fv.commodity_hs == "30771"
    assert fv.period == 2023
    assert fv.cvs == pytest.approx(0.38)
    assert fv.notification_count == 7
    assert fv.cvs_mode == "sci_crs_his"


def test_feature_extractor_derived_includes_rolling_and_delta():
    from defensefood.agent.predictive import extract_corridor_features

    state = _three_period_state()
    fv = extract_corridor_features(
        state, commodity_hs="30771", destination_m49=250, origin_m49=724, period=2023
    )
    assert fv is not None
    d = fv.derived
    assert d["commodity_chapter"] == "30"
    assert d["years_of_history"] == 2  # 2021 and 2022 precede 2023
    assert d["periods_observed"] == [2021, 2022, 2023]
    assert d["cvs_delta_yoy"] == pytest.approx(0.38 - 0.34)
    assert d["cvs_delta_2y"] == pytest.approx(0.38 - 0.30)
    assert d["his_delta_yoy"] == pytest.approx(0.45 - 0.40)
    assert d["notif_delta_yoy"] == 2
    assert d["notif_cadence_shape"] == "rising"
    # Cumulative + rolling.
    assert d["notif_cumulative"] == 3 + 5 + 7
    assert d["cvs_rolling_mean_3"] == pytest.approx((0.30 + 0.34 + 0.38) / 3)


def test_feature_extractor_peer_z_scores_use_chapter_destination():
    from defensefood.agent.predictive import extract_corridor_features

    state = _three_period_state()
    fv = extract_corridor_features(
        state, commodity_hs="30771", destination_m49=250, origin_m49=724, period=2023
    )
    assert fv is not None
    d = fv.derived
    # Peers at 2023: LANE_B cvs=0.30, LANE_C cvs=0.25 → mean=0.275, std≈0.025
    # LANE_A cvs=0.38 → z ≈ (0.38 - 0.275) / 0.025 ≈ 4.2
    assert "cvs_z_peer" in d
    assert d["cvs_z_peer"] > 1.0
    assert d["peer_count"] == 2


def test_feature_extractor_is_causal_for_earlier_periods():
    """Asking for the lane at 2021 must NOT see 2022 or 2023 data."""
    from defensefood.agent.predictive import extract_corridor_features

    state = _three_period_state()
    fv = extract_corridor_features(
        state, commodity_hs="30771", destination_m49=250, origin_m49=724, period=2021
    )
    assert fv is not None
    d = fv.derived
    assert d["years_of_history"] == 0
    assert d["periods_observed"] == [2021]
    # No yoy delta possible.
    assert "cvs_delta_yoy" not in d


def test_feature_extractor_returns_none_when_period_missing():
    from defensefood.agent.predictive import extract_corridor_features

    state = _three_period_state()
    assert (
        extract_corridor_features(
            state,
            commodity_hs="99999",
            destination_m49=250,
            origin_m49=724,
            period=2023,
        )
        is None
    )


# ── baseline forecasters ────────────────────────────────────────────────


def test_persistence_forecaster_predicts_last_cvs():
    from defensefood.agent.predictive import (
        PersistenceForecaster,
        extract_corridor_features,
    )
    from defensefood.agent.predictive.forecaster import ForecastInput

    state = _three_period_state()
    seq = [
        extract_corridor_features(
            state, commodity_hs="30771", destination_m49=250, origin_m49=724, period=p
        )
        for p in (2021, 2022, 2023)
    ]
    seq = [fv for fv in seq if fv is not None]

    forecaster = PersistenceForecaster()
    out = forecaster.predict(
        ForecastInput(
            commodity_hs="30771",
            destination_m49=250,
            origin_m49=724,
            as_of_period=2023,
            history=seq,
        )
    )
    assert out.target_period == 2024
    assert out.cvs_point == pytest.approx(0.38)
    # No residuals fit yet → no interval.
    assert out.cvs_low is None
    assert out.cvs_high is None
    assert out.direction in ("rising", "stable", "falling")


def test_persistence_forecaster_interval_after_residual_fit():
    from defensefood.agent.predictive import PersistenceForecaster
    from defensefood.agent.predictive.feature_extractor import CorridorFeatureVector
    from defensefood.agent.predictive.forecaster import ForecastInput

    forecaster = PersistenceForecaster()
    forecaster.fit_residuals([0.02, -0.01, 0.03, -0.02, 0.0])
    out = forecaster.predict(
        ForecastInput(
            commodity_hs="30771",
            destination_m49=250,
            origin_m49=724,
            as_of_period=2023,
            history=[
                CorridorFeatureVector(
                    commodity_hs="30771",
                    destination_m49=250,
                    origin_m49=724,
                    period=2023,
                    cvs=0.4,
                )
            ],
        )
    )
    assert out.cvs_point is not None
    assert out.cvs_low is not None
    assert out.cvs_high is not None
    assert out.cvs_low < out.cvs_point < out.cvs_high


def test_persistence_handles_empty_history_gracefully():
    from defensefood.agent.predictive import PersistenceForecaster
    from defensefood.agent.predictive.forecaster import ForecastInput

    out = PersistenceForecaster().predict(
        ForecastInput(
            commodity_hs="30771",
            destination_m49=250,
            origin_m49=724,
            as_of_period=2023,
            history=[],
        )
    )
    assert out.cvs_point is None
    assert "insufficient_history" in out.notes


def test_chapter_median_forecaster_uses_peer_lanes():
    from defensefood.agent.predictive import (
        ChapterMedianForecaster,
        extract_corridor_features,
    )
    from defensefood.agent.predictive.forecaster import ForecastInput

    state = _three_period_state()
    seq = [
        extract_corridor_features(
            state, commodity_hs="30771", destination_m49=250, origin_m49=724, period=p
        )
        for p in (2021, 2022, 2023)
    ]
    seq = [fv for fv in seq if fv is not None]

    forecaster = ChapterMedianForecaster(state=state)
    out = forecaster.predict(
        ForecastInput(
            commodity_hs="30771",
            destination_m49=250,
            origin_m49=724,
            as_of_period=2023,
            history=seq,
        )
    )
    # 2023 peers (LANE_B=0.30, LANE_C=0.25) → median 0.275.
    assert out.cvs_point == pytest.approx(0.275)
    assert out.target_period == 2024
    assert any("chapter_median" in d for d in out.drivers)


# ── back-test harness ───────────────────────────────────────────────────


def test_walk_forward_produces_one_walk_per_eligible_target():
    """3 populated periods → 2 walks (2022 from 2021; 2023 from 2021+2022)."""
    from defensefood.agent.predictive import PersistenceForecaster, walk_forward

    state = _three_period_state()
    walks = walk_forward(state, forecaster_factory=PersistenceForecaster)
    assert len(walks) == 2
    assert [w.target_period for w in walks] == [2022, 2023]
    # Each walk scored every lane that exists in both train + target.
    for w in walks:
        assert w.n_cases >= 1
        assert w.n_with_label >= 1
        assert w.mae is not None
        assert w.rmse is not None


def test_run_backtest_rejects_target_before_train_max():
    """Defensive: target must be strictly after the last train period."""
    from defensefood.agent.predictive import PersistenceForecaster, run_backtest

    state = _three_period_state()
    with pytest.raises(ValueError, match="must all precede"):
        run_backtest(
            state,
            forecaster=PersistenceForecaster(),
            train_periods=[2022, 2023],
            target_period=2022,
        )


def test_fit_residuals_calibrates_persistence_interval():
    """After residual fit, predictions carry a non-degenerate 80% interval."""
    from defensefood.agent.predictive import (
        PersistenceForecaster,
        fit_residuals_from_training,
        extract_corridor_features,
    )
    from defensefood.agent.predictive.forecaster import ForecastInput

    state = _three_period_state()
    forecaster = PersistenceForecaster()
    fit_residuals_from_training(
        state, forecaster=forecaster, train_periods=[2021, 2022]
    )
    assert forecaster.residual_std is not None  # at least one residual landed
    seq = [
        extract_corridor_features(
            state, commodity_hs="30771", destination_m49=250, origin_m49=724, period=2022
        )
    ]
    out = forecaster.predict(
        ForecastInput(
            commodity_hs="30771",
            destination_m49=250,
            origin_m49=724,
            as_of_period=2022,
            history=[fv for fv in seq if fv is not None],
        )
    )
    assert out.cvs_low is not None
    assert out.cvs_high is not None


def test_backtest_target_must_be_in_history():
    """If target_period has no entries, n_cases is zero — but no crash."""
    from defensefood.agent.predictive import PersistenceForecaster, run_backtest

    state = _three_period_state()
    result = run_backtest(
        state,
        forecaster=PersistenceForecaster(),
        train_periods=[2021, 2022],
        target_period=2099,
    )
    assert result.n_cases == 0
    assert result.mae is None


# ── CLI smoke ───────────────────────────────────────────────────────────


def _run_cli(argv: list[str], tmp_output: Any = None) -> tuple[int, str]:
    """Invoke the predictive CLI in-process and capture stdout."""
    import io
    import contextlib

    from script import predictive

    if tmp_output is not None:
        original = predictive.OUTPUT_DIR
        predictive.OUTPUT_DIR = tmp_output
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = predictive.main(argv)
    finally:
        if tmp_output is not None:
            predictive.OUTPUT_DIR = original  # noqa: F821
    return rc, buf.getvalue()


def test_cli_coverage_human_output(tmp_path, monkeypatch):
    """coverage subcommand prints per-period counts."""
    from defensefood.api import dependencies as deps

    deps._state = None
    monkeypatch.setattr(deps, "_load_data", lambda s: None)
    state = _three_period_state()
    state.notifications = []
    state.scoring_config = None
    state.dependency_history = {}
    state.corridors = []
    state.notifications_by_corridor = {}
    state.coverage = {}
    deps._state = state

    rc, out = _run_cli(["coverage"])
    assert rc == 0
    assert "2021" in out and "2022" in out and "2023" in out


def test_cli_backtest_writes_reports(tmp_path, monkeypatch):
    """backtest subcommand writes a JSON + CSV report and prints aggregates."""
    from defensefood.api import dependencies as deps

    deps._state = None
    monkeypatch.setattr(deps, "_load_data", lambda s: None)
    state = _three_period_state()
    state.notifications = []
    deps._state = state

    rc, out = _run_cli(["backtest", "--forecaster", "persistence"], tmp_output=tmp_path)
    assert rc == 0
    assert "persistence" in out
    assert "Walk-forward back-test" in out
    # Files written.
    written = list(tmp_path.glob("predictive_eval_*.json"))
    assert len(written) == 1
    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert "persistence" in payload["forecasters"]
    walks = payload["forecasters"]["persistence"]["walks"]
    assert len(walks) == 2
    # CSV exists too.
    assert list(tmp_path.glob("predictive_eval_*.csv"))
