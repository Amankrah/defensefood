"""
Forecaster interface (Phase 5.4 scaffold).

Defines the contract a future predictive epic will implement. No model is
provided; the type hints are what the harness, the agent, and the UI will
all rely on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from defensefood.agent.predictive.feature_extractor import CorridorFeatureVector


@dataclass
class ForecastInput:
    """A single forecast query: a corridor's history up to ``as_of_period``."""

    commodity_hs: str
    destination_m49: int
    origin_m49: int
    as_of_period: int
    history: list[CorridorFeatureVector]


@dataclass
class ForecastOutput:
    """The forecaster's reading on what happens next."""

    target_period: int
    cvs_point: Optional[float] = None
    cvs_low: Optional[float] = None
    cvs_high: Optional[float] = None
    his_point: Optional[float] = None
    direction: str = "stable"  # rising | falling | stable
    confidence: str = "low"     # low | med | high
    drivers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class Forecaster(Protocol):
    """Anything that turns a corridor's history into a next-period reading.

    The future epic provides concrete implementations: a calibrated linear
    baseline, a gradient-boosted tree on engineered features, and (later)
    a sequence model. All conform to this Protocol so the eval harness and
    the agent's anomaly explainer can swap them out.
    """

    def predict(self, query: ForecastInput) -> ForecastOutput: ...


__all__ = ["ForecastInput", "ForecastOutput", "Forecaster"]
