"""
Shared FastAPI dependencies.

Provides singleton access to data and pipeline results
that are loaded once at startup and shared across requests.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from defensefood_core import RasffNotification
from defensefood.ingestion.comtrade import load_merged_trade_data
from defensefood.ingestion.rasff import Corridor, RasffSummary, extract_corridors, load_rasff_data
from defensefood.models.scores import ScoringConfig
from defensefood.pipeline.hazard_pipeline import build_notifications, compute_corridor_hazard


@dataclass
class AppState:
    """Application-wide state loaded at startup."""
    trade_df: Optional[pd.DataFrame] = None
    rasff_df: Optional[pd.DataFrame] = None
    corridors: list[Corridor] = field(default_factory=list)
    rasff_summary: Optional[RasffSummary] = None
    notifications: list[RasffNotification] = field(default_factory=list)
    corridor_metrics: list[dict] = field(default_factory=list)
    scoring_config: ScoringConfig = field(default_factory=ScoringConfig)
    current_period: int = 0


_state: Optional[AppState] = None


def get_state() -> AppState:
    """Get the global app state (lazy-initialized)."""
    global _state
    if _state is None:
        _state = AppState()
        _load_data(_state)
    return _state


def _load_data(state: AppState) -> None:
    """Load all data sources into app state."""
    # Load trade data
    try:
        state.trade_df = load_merged_trade_data()
    except FileNotFoundError:
        state.trade_df = pd.DataFrame()

    # Load RASFF data and run hazard pipeline
    try:
        state.rasff_df = load_rasff_data()
        state.corridors, state.rasff_summary = extract_corridors(state.rasff_df)
        state.notifications = build_notifications(state.corridors)

        # Determine current period
        periods = [n.period for n in state.notifications if n.period > 0]
        state.current_period = max(periods) if periods else 202600

        # Compute hazard metrics for each unique corridor
        seen = set()
        for c in state.corridors:
            key = (c.commodity_hs, c.destination_m49, c.origin_m49)
            if key in seen or not c.commodity_hs:
                continue
            seen.add(key)

            metrics = compute_corridor_hazard(
                state.notifications, c.commodity_hs, c.destination_m49,
                c.origin_m49, state.current_period,
            )
            metrics["commodity_hs"] = c.commodity_hs
            metrics["commodity_name"] = c.commodity_name
            metrics["destination_m49"] = c.destination_m49
            metrics["destination_country"] = c.destination_country
            metrics["origin_m49"] = c.origin_m49
            metrics["origin_country"] = c.origin_country
            state.corridor_metrics.append(metrics)

    except FileNotFoundError:
        pass


def reload_data() -> AppState:
    """Force reload all data sources."""
    global _state
    _state = AppState()
    _load_data(_state)
    return _state
