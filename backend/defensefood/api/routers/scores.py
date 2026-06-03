"""Scoring configuration and results endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from defensefood.api.dependencies import AppState, get_state
from defensefood.models.scores import ScoringConfig
from defensefood.pipeline.hazard_pipeline import compute_corridor_hazard
from defensefood.pipeline.scoring_pipeline import run_scoring_pipeline

router = APIRouter(prefix="/scoring", tags=["scoring"])


def _rebuild_hazard_metrics(state: AppState) -> None:
    """Recompute HIS/HDI for every corridor with the current alpha_decay.

    Preserves all non-hazard fields already attached to each metric entry
    (dependency, consumption, trade-flow, market-presence) so callers don't
    lose enrichment when alpha changes.
    """
    from defensefood.ingestion.rasff import _extract_hazard_categories

    hazard_category_map: dict[str, str] = {}
    for c in state.corridors:
        if c.reference and c.reference not in hazard_category_map:
            hazard_category_map[c.reference] = c.hazard_category

    alpha = state.scoring_config.alpha_decay
    by_key = {
        (m.get("commodity_hs"), m.get("destination_m49"), m.get("origin_m49")): m
        for m in state.corridor_metrics
    }
    hazard_fields = (
        "his", "hdi", "notification_count", "severity_total",
        "hazard_breakdown",
    )
    for c in state.corridors:
        if not c.commodity_hs:
            continue
        key = (c.commodity_hs, c.destination_m49, c.origin_m49)
        existing = by_key.get(key)
        if existing is None:
            continue
        fresh = compute_corridor_hazard(
            state.notifications, c.commodity_hs, c.destination_m49,
            c.origin_m49, state.current_period,
            alpha=alpha,
            hazard_category_map=hazard_category_map,
        )
        for f in hazard_fields:
            if f in fresh:
                existing[f] = fresh[f]


@router.get("/config")
def get_scoring_config(state: AppState = Depends(get_state)):
    """Get current scoring configuration."""
    return state.scoring_config.model_dump()


@router.put("/config")
def update_scoring_config(
    config: ScoringConfig,
    recompute: bool = Query(
        True,
        description=(
            "When true (default) re-run scoring immediately after updating the "
            "config; also rebuilds hazard metrics if alpha_decay changed. Set "
            "false to stage a config without recomputing (admin workflow)."
        ),
    ),
    state: AppState = Depends(get_state),
):
    """Update scoring configuration. Recomputes by default."""
    prior = state.scoring_config
    state.scoring_config = config

    alpha_changed = prior.alpha_decay != config.alpha_decay
    hazard_recomputed = False
    corridors_scored = 0

    if recompute:
        if alpha_changed:
            _rebuild_hazard_metrics(state)
            hazard_recomputed = True
        scored = run_scoring_pipeline(
            [c.copy() for c in state.corridor_metrics],
            config,
        )
        state.corridor_metrics = scored
        corridors_scored = len(scored)

    return {
        "status": "updated",
        "config": config.model_dump(),
        "hazard_recomputed": hazard_recomputed,
        "corridors_scored": corridors_scored,
        "recompute": recompute,
    }


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
