"""Predictive subsystem (Phase 1: baselines + walk-forward back-test).

Public surface:

- :func:`build_scored_history` (Phase 0 precondition) materialises per-period
  CVS so the rest of this module has training labels.
- :func:`extract_corridor_features` builds a feature vector for one
  ``(lane, period)`` pair, respecting causality.
- :class:`PersistenceForecaster` and :class:`ChapterMedianForecaster` are
  the Phase 1 baselines; ``build_forecaster`` is the factory the CLI uses.
- :func:`run_backtest` runs a single train/target fold; :func:`walk_forward`
  iterates folds across the whole snapshot.
"""

from defensefood.agent.predictive.baselines import (
    ChapterMedianForecaster,
    PersistenceForecaster,
    build_forecaster,
)
from defensefood.agent.predictive.eval_harness import (
    BackTestCase,
    BackTestResult,
    fit_residuals_from_training,
    prepare_forecaster,
    run_backtest,
    walk_forward,
)
from defensefood.agent.predictive.feature_extractor import (
    CorridorFeatureVector,
    extract_corridor_features,
)
from defensefood.agent.predictive.forecaster import (
    Forecaster,
    ForecastInput,
    ForecastOutput,
)
from defensefood.agent.predictive.historical_snapshots import (
    build_scored_history,
    coverage_summary,
    lane_history,
)

__all__ = [
    "BackTestCase",
    "BackTestResult",
    "ChapterMedianForecaster",
    "CorridorFeatureVector",
    "ForecastInput",
    "ForecastOutput",
    "Forecaster",
    "PersistenceForecaster",
    "build_forecaster",
    "build_scored_history",
    "coverage_summary",
    "extract_corridor_features",
    "fit_residuals_from_training",
    "lane_history",
    "prepare_forecaster",
    "run_backtest",
    "walk_forward",
]
