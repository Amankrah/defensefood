"""
Follow-up to Phases 2 + 3 — production swap + lightgbm_lite ablation +
``cliff`` CLI subcommand.

Three groups:

1. Production swap: the startup wiring builds a persistence forecaster,
   not a LightGBM one. Driven by the 2026-06-07 backtest result where
   persistence beat LightGBM on MAE.
2. ``lightgbm_lite`` variant: same model as ``"lightgbm"`` but drops the
   high-cardinality ``commodity_hs`` from the categorical feature list.
   The factory + CLI dispatch the variant correctly and fit/predict still
   work end-to-end.
3. ``cliff`` CLI subcommand: surfaces the largest per-lane CVS deltas for
   a chosen period. Used to investigate the 2023 degradation across all
   forecasters in the backtest.
"""

from __future__ import annotations

import contextlib
import io
import json
from types import SimpleNamespace
from typing import Any

import pytest


# ── shared fixture (same shape as Phase 2's 15-lane × 4-period state) ──


def _entry(
    *, period: int, hs: str, dest: int, origin: int, cvs: float,
    his: float = 0.3, notif: int = 0, mode: str = "sci_crs_his",
    commodity_name: str = "Mussels", origin_country: str = "Spain",
) -> dict[str, Any]:
    return {
        "commodity_hs": hs, "destination_m49": dest, "origin_m49": origin,
        "commodity_name": commodity_name,
        "destination_country": "France", "origin_country": origin_country,
        "period": period, "cvs": cvs, "cvs_mode": mode, "his": his,
        "sci": 1.0, "ocs": 0.4, "bdi": 0.5, "hhi": 0.4, "idr": 0.7,
        "notification_count": notif, "severity_total": float(notif),
        "hdi": 0.1, "market_presence": "confirmed", "provenance": "faostat",
        "idr_gt_1": False, "bilateral_import_kg": 1_000_000.0,
    }


def _fixture_state() -> SimpleNamespace:
    """15 lanes × 4 periods. Lanes 30* are 'rising' chapter; 100* are 'stable'."""
    lanes_30 = [
        ("30771", 250, 724, "Spain"), ("30772", 250, 380, "Italy"),
        ("30773", 250, 528, "Netherlands"), ("30774", 250, 56, "Belgium"),
        ("30781", 250, 620, "Portugal"), ("30782", 250, 372, "Ireland"),
        ("30791", 250, 826, "UK"),
    ]
    lanes_10 = [
        ("100590", 250, 724, "Spain"), ("100630", 250, 380, "Italy"),
        ("100640", 250, 528, "Netherlands"), ("100120", 250, 56, "Belgium"),
        ("100190", 250, 620, "Portugal"), ("100210", 250, 372, "Ireland"),
        ("100290", 250, 826, "UK"), ("100300", 250, 826, "UK"),
    ]
    scored: dict[int, dict[tuple[str, int, int], dict]] = {}
    for period in (2020, 2021, 2022, 2023):
        snap = {}
        offset = period - 2020
        for hs, dest, origin, country in lanes_30:
            jitter = (hash(hs + str(origin)) % 7) * 0.005
            snap[(hs, dest, origin)] = _entry(
                period=period, hs=hs, dest=dest, origin=origin,
                cvs=min(0.9, 0.20 + 0.04 * offset + jitter),
                his=0.25 + 0.05 * offset, notif=1 + offset,
                origin_country=country,
            )
        for hs, dest, origin, country in lanes_10:
            jitter = (hash(hs + str(origin)) % 7) * 0.005
            snap[(hs, dest, origin)] = _entry(
                period=period, hs=hs, dest=dest, origin=origin,
                cvs=0.15 + jitter, his=0.12, notif=offset, mode="sci_his",
                commodity_name="Rice", origin_country=country,
            )
        scored[period] = snap

    corridor_metrics = []
    for (hs, dest, origin), entry in scored[2023].items():
        corridor_metrics.append(
            {
                "commodity_hs": hs, "destination_m49": dest,
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


# ── A: production swap ────────────────────────────────────────────────


def test_startup_wires_persistence_not_lightgbm():
    """Production forecaster is PERSISTENCE, not LightGBM.

    Source-level regression pin. The startup path (``_build_research_indices``)
    rebuilds dependency_history from ``trade_df`` and is too heavy to invoke
    from a unit test, so we assert the production-forecaster constant via
    source inspection. If someone swaps it back to ``"lightgbm"`` this fires
    immediately.

    Reason for the swap: the 2026-06-07 backtest showed persistence MAE
    0.0215 vs LightGBM MAE 0.0249 (15.8% worse), with LightGBM's 80%
    interval covering only 56% of actuals.
    """
    import inspect
    from defensefood.api import dependencies as deps_module

    deps_source = inspect.getsource(deps_module)
    assert 'PRODUCTION_FORECASTER = "persistence"' in deps_source
    assert 'PRODUCTION_FORECASTER = "lightgbm"' not in deps_source
    # And the wiring actually uses the constant rather than a hard-coded
    # string somewhere else.
    assert "build_forecaster(PRODUCTION_FORECASTER" in deps_source


def test_persistence_forecaster_fits_residuals_and_predicts():
    """Sanity check the production model end to end: train residuals get
    calibrated into the 80% interval, predict returns a finite point and a
    bounded interval that contains the point."""
    from defensefood.agent.predictive.baselines import PersistenceForecaster
    from defensefood.agent.predictive import extract_corridor_features
    from defensefood.agent.predictive.forecaster import ForecastInput

    state = _fixture_state()
    forecaster = PersistenceForecaster()
    # Walk-forward style: feed it residuals from the train fold.
    forecaster.fit_residuals([0.01, -0.02, 0.005, 0.015, -0.01])
    assert forecaster.residual_std is not None
    assert forecaster.residual_std > 0

    seq = [
        extract_corridor_features(
            state, commodity_hs="30771",
            destination_m49=250, origin_m49=724, period=p,
        )
        for p in (2020, 2021, 2022)
    ]
    seq = [fv for fv in seq if fv is not None]
    out = forecaster.predict(
        ForecastInput(
            commodity_hs="30771",
            destination_m49=250,
            origin_m49=724,
            as_of_period=2022,
            history=seq,
        )
    )
    assert out.cvs_point is not None
    assert out.cvs_low is not None and out.cvs_high is not None
    assert out.cvs_low <= out.cvs_point <= out.cvs_high
    # 80% interval should be a meaningful width but not enormous.
    assert 0.0 < (out.cvs_high - out.cvs_low) < 0.5


# ── B: lightgbm_lite ablation ─────────────────────────────────────────


def test_build_forecaster_dispatches_lightgbm_lite_variant():
    from defensefood.agent.predictive import build_forecaster
    from defensefood.agent.predictive.lightgbm_forecaster import (
        LightGBMForecaster,
    )

    f = build_forecaster("lightgbm_lite")
    assert isinstance(f, LightGBMForecaster)
    assert f.include_hs_identity is False
    assert f.name == "lightgbm_lite"

    # Full variant for comparison.
    full = build_forecaster("lightgbm")
    assert isinstance(full, LightGBMForecaster)
    assert full.include_hs_identity is True


def test_lightgbm_lite_column_count_drops_hs_categorical():
    """The lite variant has one fewer column than the full variant — the
    commodity_hs categorical is dropped."""
    from defensefood.agent.predictive.lightgbm_forecaster import (
        LightGBMForecaster,
    )

    full = LightGBMForecaster(include_hs_identity=True)
    lite = LightGBMForecaster(include_hs_identity=False)
    full_cols = full._column_names()
    lite_cols = lite._column_names()
    assert len(full_cols) == len(lite_cols) + 1
    assert "commodity_hs" in full_cols
    assert "commodity_hs" not in lite_cols
    # The chapter categorical stays — that's the low-cardinality substitute.
    assert "commodity_chapter" in lite_cols


def test_lightgbm_lite_fits_and_predicts_end_to_end():
    from defensefood.agent.predictive.lightgbm_forecaster import (
        LightGBMForecaster,
    )
    from defensefood.agent.predictive import extract_corridor_features
    from defensefood.agent.predictive.forecaster import ForecastInput

    state = _fixture_state()
    forecaster = LightGBMForecaster(
        include_hs_identity=False, min_data_in_leaf=1, num_iterations=20
    )
    forecaster.fit(state, [2020, 2021, 2022])
    assert forecaster._is_fit

    seq = [
        extract_corridor_features(
            state, commodity_hs="30771",
            destination_m49=250, origin_m49=724, period=p,
        )
        for p in (2020, 2021, 2022)
    ]
    seq = [fv for fv in seq if fv is not None]
    out = forecaster.predict(
        ForecastInput(
            commodity_hs="30771",
            destination_m49=250,
            origin_m49=724,
            as_of_period=2022,
            history=seq,
        )
    )
    assert out.cvs_point is not None
    assert 0.0 <= out.cvs_point <= 1.0
    assert out.cvs_low <= out.cvs_point <= out.cvs_high


# ── C: cliff CLI subcommand ───────────────────────────────────────────


def _run_cli(argv: list[str], tmp_output=None, monkeypatch=None) -> tuple[int, str]:
    from defensefood.api import dependencies as deps
    from script import predictive

    state = _fixture_state()
    deps._state = state
    # Sidestep _load_data so the production data path doesn't fire.
    if monkeypatch is not None:
        monkeypatch.setattr(deps, "_load_data", lambda s: None)
    if tmp_output is not None:
        predictive.OUTPUT_DIR = tmp_output

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = predictive.main(argv)
    return rc, buf.getvalue()


def test_cliff_cli_prints_top_movers_for_default_period(monkeypatch):
    rc, out = _run_cli(["cliff", "--top-k", "5"], monkeypatch=monkeypatch)
    assert rc == 0
    # Default period is the latest (2023) compared to 2022.
    assert "2022" in out and "2023" in out
    assert "median" in out
    assert "Top 5 movers" in out


def test_cliff_cli_json_output_has_full_movers_payload(monkeypatch):
    rc, out = _run_cli(
        ["cliff", "--period", "2023", "--top-k", "3", "--json"],
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    payload = json.loads(out)
    assert payload["prior_period"] == 2022
    assert payload["target_period"] == 2023
    assert len(payload["top_movers"]) == 3
    for mover in payload["top_movers"]:
        assert "cvs_delta" in mover
        assert "his_delta" in mover
        assert "notif_delta" in mover


def test_cliff_cli_rejects_period_with_no_prior(monkeypatch):
    """Earliest period in history → no prior → non-zero exit + clear error."""
    rc, out = _run_cli(
        ["cliff", "--period", "2020"], monkeypatch=monkeypatch
    )
    assert rc != 0


def test_cliff_cli_rejects_unknown_period(monkeypatch):
    rc, out = _run_cli(
        ["cliff", "--period", "1999"], monkeypatch=monkeypatch
    )
    assert rc != 0
