"""Scoring configuration and results endpoints."""

from fastapi import APIRouter, Depends

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
def recalculate_scores(state: AppState = Depends(get_state)):
    """Trigger full re-scoring with current config."""
    scored = run_scoring_pipeline(
        state.corridor_metrics.copy(),
        state.scoring_config,
    )

    return {
        "status": "recalculated",
        "corridors_scored": len(scored),
        "top_10": scored[:10],
    }
