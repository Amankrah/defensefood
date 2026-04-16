"""Scoring configuration and results endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from defensefood.api.dependencies import AppState, get_state
from defensefood.models.scores import ScoringConfig
from defensefood.pipeline.scoring_pipeline import run_scoring_pipeline

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.get("/config")
def get_scoring_config(state: AppState = Depends(get_state)):
    """Get current scoring configuration."""
    return state.scoring_config.model_dump()


@router.put("/config")
def update_scoring_config(
    config: ScoringConfig,
    state: AppState = Depends(get_state),
):
    """Update scoring configuration."""
    state.scoring_config = config
    return {"status": "updated", "config": config.model_dump()}


@router.post("/recalculate")
def recalculate_scores(
    config: Optional[ScoringConfig] = None,
    limit: int = Query(1000, ge=1, le=5000),
    state: AppState = Depends(get_state),
):
    """Trigger full re-scoring. Optionally pass a config to override current settings."""
    effective_config = config or state.scoring_config
    if config:
        state.scoring_config = config

    scored = run_scoring_pipeline(
        [c.copy() for c in state.corridor_metrics],
        effective_config,
    )

    # Persist scored results back to state
    state.corridor_metrics = scored

    return {
        "status": "recalculated",
        "corridors_scored": len(scored),
        "corridors": scored[:limit],
    }
