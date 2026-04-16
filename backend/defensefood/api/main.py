"""
DefenseFood API -- FastAPI application.

EU Food Fraud Vulnerability Intelligence System.
Serves corridor metrics, hazard signals, and vulnerability scores
computed by the Rust defensefood_core engine.
"""

import math
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


def _sanitize_floats(obj: Any) -> Any:
    """Replace NaN/Infinity with None so JSON serialisation succeeds."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_floats(v) for v in obj]
    return obj


class SafeJSONResponse(JSONResponse):
    """JSONResponse that converts NaN/Infinity to null."""

    def render(self, content: Any) -> bytes:
        return super().render(_sanitize_floats(content))

from defensefood.api.dependencies import get_state
from defensefood.pipeline.scoring_pipeline import run_scoring_pipeline


def _cors_allow_origins() -> list[str]:
    """Origins allowed for browser clients (comma-separated env or dev defaults)."""
    raw = os.environ.get("DEFENSEFOOD_CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
from defensefood.api.routers import (
    commodities,
    corridors,
    countries,
    hazards,
    health,
    network,
    scores,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load data on startup."""
    state = get_state()
    print(f"Loaded {len(state.corridor_metrics)} corridor metrics")
    print(f"Loaded {len(state.notifications)} RASFF notifications")
    if state.trade_df is not None:
        print(f"Loaded {len(state.trade_df)} trade records")
    if state.corridor_metrics:
        state.corridor_metrics = run_scoring_pipeline(
            [c.copy() for c in state.corridor_metrics],
            state.scoring_config,
        )
        print(f"Initial CVS scoring applied to {len(state.corridor_metrics)} corridors")
    yield


app = FastAPI(
    title="DefenseFood API",
    description="EU Food Fraud Vulnerability Intelligence System",
    version="0.1.0",
    lifespan=lifespan,
    default_response_class=SafeJSONResponse,
)

# CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router, prefix="/api/v1")
app.include_router(corridors.router, prefix="/api/v1")
app.include_router(countries.router, prefix="/api/v1")
app.include_router(commodities.router, prefix="/api/v1")
app.include_router(hazards.router, prefix="/api/v1")
app.include_router(scores.router, prefix="/api/v1")
app.include_router(network.router, prefix="/api/v1")


@app.get("/")
def root():
    return {
        "name": "DefenseFood API",
        "version": "0.1.0",
        "docs": "/docs",
        "api_base": "/api/v1",
    }
