"""Health check endpoint."""

from fastapi import APIRouter

import defensefood_core

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "rust_module": "defensefood_core",
        "rust_submodules": [
            "dependency", "consumption", "hazard",
            "trade_flow", "network", "scoring",
        ],
        "version": "0.1.0",
    }
