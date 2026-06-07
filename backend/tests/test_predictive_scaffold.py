"""Predictive subsystem — package import + scaffold sanity.

Originally written in Phase 5.4 when forecaster + harness were stubs. The
deeper behavioural tests now live in:

- ``test_historical_snapshots.py`` (Phase 0 — per-period CVS)
- ``test_predictive_phase1.py``    (Phase 1 — features, baselines, back-test)

This file is kept as a compile-time smoke test: every public symbol on the
package surface imports, the dataclasses construct, and the feature
extractor returns ``None`` when the lane has no scored entry.
"""

from __future__ import annotations

from types import SimpleNamespace


def test_predictive_package_imports():
    from defensefood.agent.predictive import (
        BackTestCase,
        BackTestResult,
        ChapterMedianForecaster,
        CorridorFeatureVector,
        ForecastInput,
        ForecastOutput,
        Forecaster,  # noqa: F401  (Protocol; importable)
        PersistenceForecaster,
        build_forecaster,
        build_scored_history,
        coverage_summary,
        extract_corridor_features,
        fit_residuals_from_training,
        lane_history,
        run_backtest,
        walk_forward,
    )

    # Sanity: the dataclass shapes still construct cleanly.
    fv = CorridorFeatureVector(
        commodity_hs="30771", destination_m49=250, origin_m49=724, period=2023
    )
    assert fv.commodity_hs == "30771"
    assert fv.derived == {}

    out = ForecastOutput(target_period=2024)
    assert out.direction == "stable"
    assert out.confidence == "low"

    fi = ForecastInput(
        commodity_hs="30771",
        destination_m49=250,
        origin_m49=724,
        as_of_period=2023,
        history=[fv],
    )
    assert len(fi.history) == 1
    assert isinstance(
        BackTestResult(
            forecaster_name="x", train_periods=[2022], target_period=2023
        ),
        BackTestResult,
    )
    assert isinstance(
        BackTestCase(
            commodity_hs="x",
            destination_m49=0,
            origin_m49=0,
            train_periods=[2022],
            target_period=2023,
        ),
        BackTestCase,
    )

    # Factory + functions are callable.
    assert callable(run_backtest)
    assert callable(walk_forward)
    assert callable(fit_residuals_from_training)
    assert callable(build_scored_history)
    assert callable(coverage_summary)
    assert callable(lane_history)
    assert isinstance(build_forecaster("persistence"), PersistenceForecaster)
    # ChapterMedian needs a state but should still construct via the factory.
    cm = build_forecaster("chapter_median", state=SimpleNamespace(scored_history={}))
    assert isinstance(cm, ChapterMedianForecaster)


def test_extract_corridor_features_returns_none_when_snapshot_missing():
    from defensefood.agent.predictive import extract_corridor_features

    state = SimpleNamespace(scored_history={2023: {}}, corridor_metrics=[])
    assert (
        extract_corridor_features(
            state,
            commodity_hs="999",
            destination_m49=0,
            origin_m49=0,
            period=2023,
        )
        is None
    )
