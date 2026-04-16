"""Commodity-level endpoints."""

from fastapi import APIRouter, Depends, Query

from defensefood.api.dependencies import AppState, get_state
from defensefood.ingestion.hs_codes import get_hs_codes_with_names, get_unique_hs_codes

router = APIRouter(prefix="/commodities", tags=["commodities"])


@router.get("")
def list_commodities():
    """List all tracked HS codes with commodity names."""
    mapping = get_hs_codes_with_names()
    items = [
        {"hs_code": code, "names": names}
        for code, names in sorted(mapping.items())
    ]
    return {"count": len(items), "commodities": items}


@router.get("/{hs_code}")
def get_commodity_detail(
    hs_code: str,
    state: AppState = Depends(get_state),
):
    """Get corridors for a specific commodity."""
    mapping = get_hs_codes_with_names()
    names = mapping.get(hs_code, [])

    corridors = [
        c for c in state.corridor_metrics
        if c.get("commodity_hs") == hs_code
    ]
    corridors.sort(key=lambda c: c.get("his", 0), reverse=True)

    return {
        "hs_code": hs_code,
        "names": names,
        "corridor_count": len(corridors),
        "corridors": corridors,
    }
