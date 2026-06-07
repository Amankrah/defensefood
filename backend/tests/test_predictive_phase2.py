"""
Phase 2 of the predictive epic — pooled LightGBM forecaster with quantile
prediction.

Three groups of tests:

1. Fit + predict on a synthetic multi-lane, multi-period fixture. Pinning
   the contract: predictions land in [0, 1], intervals bracket the point
   estimate, drivers list non-empty.
2. Harness integration. ``walk_forward`` calls ``forecaster.fit`` via
   ``prepare_forecaster`` for any forecaster that defines it.
3. Factory + CLI dispatch. ``build_forecaster('lightgbm')`` returns the
   right class; the CLI accepts the ``lightgbm`` choice.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest


# ── fixture: 4 periods × 15 lanes spanning two HS chapters ─────────────


def _entry(
    *,
    period: int,
    hs: str,
    dest: int,
    origin: int,
    cvs: float,
    his: float,
    notif: int,
    sci: float = 1.0,
    ocs: float = 0.4,
    bdi: float = 0.5,
    hhi: float = 0.4,
    idr: float = 0.7,
    mode: str = "sci_crs_his",
    bilateral_kg: float = 1_000_000.0,
    market_presence: str = "confirmed",
    provenance: str = "faostat",
    commodity_name: str = "Mussels",
    destination_country: str = "France",
    origin_country: str = "Spain",
) -> dict[str, Any]:
    return {
        "commodity_hs": hs,
        "destination_m49": dest,
        "origin_m49": origin,
        "commodity_name": commodity_name,
        "destination_country": destination_country,
        "origin_country": origin_country,
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
        "provenance": provenance,
        "idr_gt_1": False,
        "bilateral_import_kg": bilateral_kg,
    }


def _large_fixture_state() -> SimpleNamespace:
    """15 lanes × 4 periods (2020-2023) of synthetic but trend-consistent
    scored history. Two HS chapters (30, 10) into one destination (250).

    The CVS trajectories follow simple rules so the model has something to
    learn:
    - Chapter 30 lanes: rising CVS over time (notif growth drives HIS up).
    - Chapter 10 lanes: stable CVS.
    """
    lanes_30 = [
        ("30771", 250, 724, "Spain"),
        ("30772", 250, 380, "Italy"),
        ("30773", 250, 528, "Netherlands"),
        ("30774", 250, 56, "Belgium"),
        ("30781", 250, 620, "Portugal"),
        ("30782", 250, 372, "Ireland"),
        ("30791", 250, 826, "UK"),
    ]
    lanes_10 = [
        ("100590", 250, 724, "Spain"),
        ("100630", 250, 380, "Italy"),
        ("100640", 250, 528, "Netherlands"),
        ("100120", 250, 56, "Belgium"),
        ("100190", 250, 620, "Portugal"),
        ("100210", 250, 372, "Ireland"),
        ("100290", 250, 826, "UK"),
        ("100300", 250, 826, "UK"),
    ]

    scored: dict[int, dict[tuple[str, int, int], dict]] = {}
    for period in (2020, 2021, 2022, 2023):
        snap = {}
        # Chapter 30: rising CVS, more notifications each year.
        year_offset = period - 2020
        for hs, dest, origin, country in lanes_30:
            base_cvs = 0.20 + 0.04 * year_offset
            # Add some lane variation so the model isn't trivially fittable.
            lane_jitter = (hash(hs + str(origin)) % 7) * 0.005
            snap[(hs, dest, origin)] = _entry(
                period=period,
                hs=hs,
                dest=dest,
                origin=origin,
                origin_country=country,
                cvs=min(0.9, base_cvs + lane_jitter),
                his=0.25 + 0.05 * year_offset,
                notif=1 + year_offset,
                commodity_name="Mussels",
            )
        # Chapter 10: stable CVS.
        for hs, dest, origin, country in lanes_10:
            lane_jitter = (hash(hs + str(origin)) % 7) * 0.005
            snap[(hs, dest, origin)] = _entry(
                period=period,
                hs=hs,
                dest=dest,
                origin=origin,
                origin_country=country,
                cvs=0.15 + lane_jitter,
                his=0.12,
                notif=year_offset,  # very slowly rising
                mode="sci_his",  # exercise the fallback branch in encoding
                provenance="trade_only",
                commodity_name="Rice",
            )
        scored[period] = snap

    # Build matching corridor_metrics from the latest period.
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
        notifications=[],
    )


# ── fit + predict ────────────────────────────────────────────────────────


def test_lightgbm_fits_and_predicts_in_unit_range():
    from defensefood.agent.predictive.lightgbm_forecaster import LightGBMForecaster
    from defensefood.agent.predictive import extract_corridor_features
    from defensefood.agent.predictive.forecaster import ForecastInput

    state = _large_fixture_state()
    forecaster = LightGBMForecaster(min_data_in_leaf=1, num_iterations=50)
    forecaster.fit(state, [2020, 2021, 2022])
    assert forecaster._is_fit
    assert len(forecaster._models) == 3
    assert forecaster._train_mae is not None
    assert forecaster._feature_importance

    # Predict for one lane.
    lane_key = ("30771", 250, 724)
    seq = [
        extract_corridor_features(
            state, commodity_hs=lane_key[0], destination_m49=lane_key[1],
            origin_m49=lane_key[2], period=p,
        )
        for p in (2020, 2021, 2022)
    ]
    seq = [fv for fv in seq if fv is not None]
    out = forecaster.predict(
        ForecastInput(
            commodity_hs=lane_key[0],
            destination_m49=lane_key[1],
            origin_m49=lane_key[2],
            as_of_period=2022,
            history=seq,
        )
    )
    assert out.cvs_point is not None
    assert 0.0 <= out.cvs_point <= 1.0
    assert out.cvs_low is not None and out.cvs_high is not None
    assert out.cvs_low <= out.cvs_point <= out.cvs_high
    assert out.drivers  # at least one driver listed


def test_lightgbm_returns_model_not_fitted_before_fit():
    from defensefood.agent.predictive.lightgbm_forecaster import LightGBMForecaster
    from defensefood.agent.predictive.feature_extractor import CorridorFeatureVector
    from defensefood.agent.predictive.forecaster import ForecastInput

    forecaster = LightGBMForecaster()
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
                    cvs=0.3,
                )
            ],
        )
    )
    assert out.cvs_point is None
    assert "model_not_fitted" in out.notes


def test_lightgbm_skips_fit_when_too_few_pairs():
    """Less than 4 training pairs → fit logs warning and leaves model unfit.
    Subsequent predict() returns graceful 'model_not_fitted'."""
    from defensefood.agent.predictive.lightgbm_forecaster import LightGBMForecaster

    state = SimpleNamespace(
        scored_history={
            2022: {("X", 1, 2): {"cvs": 0.3}},
            2023: {("X", 1, 2): {"cvs": 0.32}},
        },
        corridor_metrics=[],
        notifications=[],
    )
    forecaster = LightGBMForecaster(min_data_in_leaf=1, num_iterations=10)
    forecaster.fit(state, [2022])
    assert not forecaster._is_fit


def test_lightgbm_handles_unseen_categorical_at_predict_time():
    """A lane whose origin_m49 wasn't in training should still get a
    prediction — encoding falls back to a sentinel code."""
    from defensefood.agent.predictive.lightgbm_forecaster import LightGBMForecaster
    from defensefood.agent.predictive import extract_corridor_features
    from defensefood.agent.predictive.forecaster import ForecastInput

    state = _large_fixture_state()
    forecaster = LightGBMForecaster(min_data_in_leaf=1, num_iterations=20)
    forecaster.fit(state, [2020, 2021, 2022])

    # Inject a synthetic 2022 snapshot for a lane with a totally new
    # origin_m49 (999 — never seen during training).
    state.scored_history[2022][("99999", 250, 999)] = _entry(
        period=2022, hs="99999", dest=250, origin=999, cvs=0.28, his=0.15, notif=0,
    )
    fv = extract_corridor_features(
        state, commodity_hs="99999", destination_m49=250, origin_m49=999, period=2022
    )
    assert fv is not None
    out = forecaster.predict(
        ForecastInput(
            commodity_hs="99999",
            destination_m49=250,
            origin_m49=999,
            as_of_period=2022,
            history=[fv],
        )
    )
    assert out.cvs_point is not None
    assert 0.0 <= out.cvs_point <= 1.0


# ── harness integration ────────────────────────────────────────────────


def test_walk_forward_calls_fit_via_prepare_forecaster():
    """When the factory returns a LightGBMForecaster, ``walk_forward``
    must call its ``fit`` method via the prepare_forecaster hook.

    First walk (target=2021, train=[2020]) has zero training PAIRS because
    LightGBM needs (T, T+1) consecutive train periods; we skip it and
    require that walks with viable training pairs produce labelled cases.
    """
    from defensefood.agent.predictive import walk_forward
    from defensefood.agent.predictive.lightgbm_forecaster import LightGBMForecaster

    state = _large_fixture_state()

    def _factory() -> LightGBMForecaster:
        return LightGBMForecaster(min_data_in_leaf=1, num_iterations=20)

    walks = walk_forward(state, forecaster_factory=_factory)
    # 4 periods → 3 walks (target 2021, 2022, 2023).
    assert [w.target_period for w in walks] == [2021, 2022, 2023]
    # Walks with ≥ 2 training periods can fit and produce labelled cases.
    productive = [w for w in walks if len(w.train_periods) >= 2]
    assert len(productive) == 2  # targets 2022 and 2023
    for w in productive:
        assert w.forecaster_name == "lightgbm"
        assert w.n_with_label > 0
        assert w.mae is not None


def test_prepare_forecaster_skips_fit_for_persistence():
    """Persistence has no fit method; prepare_forecaster doesn't trip."""
    from defensefood.agent.predictive import (
        PersistenceForecaster,
        prepare_forecaster,
    )

    state = _large_fixture_state()
    forecaster = PersistenceForecaster()
    # Should not raise.
    prepare_forecaster(state, forecaster=forecaster, train_periods=[2020, 2021])


# ── factory + CLI ──────────────────────────────────────────────────────


def test_build_forecaster_returns_lightgbm_instance():
    from defensefood.agent.predictive import build_forecaster
    from defensefood.agent.predictive.lightgbm_forecaster import LightGBMForecaster

    f = build_forecaster("lightgbm")
    assert isinstance(f, LightGBMForecaster)


def test_cli_accepts_lightgbm_choice(tmp_path, monkeypatch):
    """script.predictive backtest --forecaster lightgbm runs end-to-end."""
    import contextlib
    import io

    from defensefood.api import dependencies as deps
    from script import predictive

    deps._state = None
    monkeypatch.setattr(deps, "_load_data", lambda s: None)
    state = _large_fixture_state()
    state.scoring_config = None
    state.dependency_history = {}
    state.corridors = []
    state.notifications_by_corridor = {}
    state.coverage = {}
    deps._state = state

    # Smaller hyperparams so the test runs fast.
    monkeypatch.setattr(predictive, "OUTPUT_DIR", tmp_path)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = predictive.main(["backtest", "--forecaster", "lightgbm"])
    assert rc == 0
    out = buf.getvalue()
    assert "lightgbm" in out
    written = list(tmp_path.glob("predictive_eval_*.json"))
    assert len(written) == 1
    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert "lightgbm" in payload["forecasters"]
    walks = payload["forecasters"]["lightgbm"]["walks"]
    assert len(walks) >= 1


def test_cli_default_runs_all_three_forecasters(tmp_path, monkeypatch):
    """No --forecaster flag → CLI runs persistence + chapter_median +
    lightgbm."""
    import contextlib
    import io

    from defensefood.api import dependencies as deps
    from script import predictive

    deps._state = None
    monkeypatch.setattr(deps, "_load_data", lambda s: None)
    state = _large_fixture_state()
    state.scoring_config = None
    state.dependency_history = {}
    state.corridors = []
    state.notifications_by_corridor = {}
    state.coverage = {}
    deps._state = state

    monkeypatch.setattr(predictive, "OUTPUT_DIR", tmp_path)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = predictive.main(["backtest"])
    assert rc == 0
    payload = json.loads(
        list(tmp_path.glob("predictive_eval_*.json"))[0].read_text(encoding="utf-8")
    )
    assert set(payload["forecasters"].keys()) == {
        "persistence", "chapter_median", "lightgbm"
    }
