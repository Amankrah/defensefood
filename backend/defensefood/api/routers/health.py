"""Health check endpoint."""

from fastapi import APIRouter, Depends

import defensefood_core

from defensefood.api.dependencies import AppState, get_state

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(state: AppState = Depends(get_state)):
    """Liveness plus lightweight data-readiness counts for ops dashboards."""
    trade_rows = 0
    if state.trade_df is not None:
        trade_rows = len(state.trade_df)
    return {
        "status": "ok",
        "rust_module": "defensefood_core",
        "rust_submodules": [
            "dependency", "consumption", "hazard",
            "trade_flow", "network", "scoring",
        ],
        "version": "0.1.0",
        "data": {
            "corridor_metrics": len(state.corridor_metrics),
            "notifications": len(state.notifications),
            "trade_rows": trade_rows,
            "current_period": state.current_period,
        },
    }
