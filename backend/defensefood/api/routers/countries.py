"""Country-level endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from defensefood.api.dependencies import AppState, get_state
from defensefood.ingestion.countries import EU27_M49, M49_COUNTRY_CODES, get_country_name

router = APIRouter(prefix="/countries", tags=["countries"])


@router.get("")
def list_countries(
    eu_only: bool = Query(False, description="Only EU27 member states"),
):
    """List all known countries with M49 codes."""
    seen = set()
    countries = []
    for name, code in sorted(M49_COUNTRY_CODES.items(), key=lambda x: x[0]):
        if code in seen or code == 0:
            continue
        seen.add(code)
        if eu_only and code not in EU27_M49:
            continue
        countries.append({
            "m49": code,
            "name": name,
            "is_eu27": code in EU27_M49,
        })
    return {"count": len(countries), "countries": countries}


@router.get("/{m49}")
def get_country_detail(
    m49: int,
    state: AppState = Depends(get_state),
):
    """Get detail for a country including corridor counts."""
    name = get_country_name(m49)
    if not name:
        return {"error": "Country not found"}

    # Count corridors where this country is destination or origin
    as_dest = [c for c in state.corridor_metrics if c.get("destination_m49") == m49]
    as_origin = [c for c in state.corridor_metrics if c.get("origin_m49") == m49]

    return {
        "m49": m49,
        "name": name,
        "is_eu27": m49 in EU27_M49,
        "corridors_as_destination": len(as_dest),
        "corridors_as_origin": len(as_origin),
    }


@router.get("/{m49}/exposure-profile")
def get_exposure_profile(
    m49: int,
    state: AppState = Depends(get_state),
):
    """Get inbound corridors for an attention country (ACEP components)."""
    name = get_country_name(m49)
    inbound = [
        c for c in state.corridor_metrics
        if c.get("destination_m49") == m49
    ]
    inbound.sort(key=lambda c: c.get("his", 0), reverse=True)

    return {
        "m49": m49,
        "name": name or "Unknown",
        "corridor_count": len(inbound),
        "corridors": inbound[:50],
    }
