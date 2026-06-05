"""Predictive subsystem scaffold (Phase 5.4).

Not yet implemented. The modules below define interfaces a future epic will
fill in. See ``README.md`` in this package for the design.
"""

from defensefood.agent.predictive.feature_extractor import (
    CorridorFeatureVector,
    extract_corridor_features,
)
from defensefood.agent.predictive.forecaster import (
    Forecaster,
    ForecastInput,
    ForecastOutput,
)
from defensefood.agent.predictive.eval_harness import (
    BackTestResult,
    run_backtest,
)

__all__ = [
    "BackTestResult",
    "CorridorFeatureVector",
    "ForecastInput",
    "ForecastOutput",
    "Forecaster",
    "extract_corridor_features",
    "run_backtest",
]
