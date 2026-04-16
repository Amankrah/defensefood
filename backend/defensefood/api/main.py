"""
DefenseFood API -- FastAPI application.

EU Food Fraud Vulnerability Intelligence System.
Serves corridor metrics, hazard signals, and vulnerability scores
computed by the Rust defensefood_core engine.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from defensefood.api.dependencies import get_state
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
    yield


app = FastAPI(
    title="DefenseFood API",
    description="EU Food Fraud Vulnerability Intelligence System",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
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
