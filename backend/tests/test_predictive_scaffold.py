"""Phase 5.4 — predictive scaffold sanity checks.

Stubs only at this stage; we verify the interfaces import, the feature
extractor produces the expected shape from a dependency_history snapshot,
and the back-test harness raises NotImplementedError as documented.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_predictive_package_imports():
    from defensefood.agent.predictive import (
        BackTestResult,
        CorridorFeatureVector,
        ForecastInput,
        ForecastOutput,
        Forecaster,  # noqa: F401  (Protocol; importable)
        extract_corridor_features,
        run_backtest,
    )

    # Sanity: the dataclass shapes are constructible.
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
    assert isinstance(BackTestResult(forecaster_name="x"), BackTestResult)
    assert callable(run_backtest)


def test_extract_corridor_features_reads_from_dependency_history():
    from defensefood.agent.predictive import extract_corridor_features

    state = SimpleNamespace(
        corridor_metrics=[
            {
                "commodity_hs": "30771",
                "destination_m49": 250,
                "origin_m49": 724,
                "cvs_mode": "sci_crs_his",
                "market_presence": "confirmed",
                "provenance": "faostat",
                "cvs": 0.345,
            }
        ],
        dependency_history={
            2023: {
                ("30771", 250, 724): {
                    "bdi": 0.6,
                    "ocs": 0.5,
                    "hhi": 0.4,
                    "idr": 0.7,
                    "sci": 1.1,
                    "his": 0.42,
                    "hdi": 0.2,
                    "notification_count": 7,
                    "cvs": 0.345,
                }
            }
        },
    )

    fv = extract_corridor_features(
        state,
        commodity_hs="30771",
        destination_m49=250,
        origin_m49=724,
        period=2023,
    )
    assert fv is not None
    assert fv.bdi == pytest.approx(0.6)
    assert fv.cvs == pytest.approx(0.345)
    assert fv.notification_count == 7
    assert fv.cvs_mode == "sci_crs_his"
    assert fv.provenance == "faostat"


def test_extract_corridor_features_returns_none_when_snapshot_missing():
    from defensefood.agent.predictive import extract_corridor_features

    state = SimpleNamespace(
        corridor_metrics=[],
        dependency_history={2023: {}},
    )
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


def test_run_backtest_raises_not_implemented():
    """The back-test harness is a Phase 5.4 scaffold placeholder."""
    from defensefood.agent.predictive import Forecaster, run_backtest

    class _NoopForecaster:
        def predict(self, query):  # type: ignore[no-untyped-def]
            raise AssertionError("should not be called by the placeholder harness")

    state = SimpleNamespace(dependency_history={}, corridor_metrics=[])
    with pytest.raises(NotImplementedError):
        run_backtest(
            state,
            forecaster=_NoopForecaster(),
            train_periods=[2022],
            target_period=2023,
        )
