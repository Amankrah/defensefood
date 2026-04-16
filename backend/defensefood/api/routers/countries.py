"""Country-level endpoints."""

from fastapi import APIRouter, Depends, Query

from defensefood.api.dependencies import AppState, get_state
from defensefood.ingestion.countries import EU27_M49, M49_COUNTRY_CODES, get_country_name
from defensefood.pipeline.network_pipeline import build_exposure_network

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


@router.get("/{m49}/orps-by-commodity")
def get_orps_by_commodity(
    m49: int,
    state: AppState = Depends(get_state),
):
    """Origin Risk Propagation Score (Eq. 33) per commodity for this origin country.

    PCC is proxied as 1.0 per destination until FAOSTAT consumption is integrated.
    """
    name = get_country_name(m49)
    if not name:
        return {"error": "Country not found"}

    hs_codes = sorted({
        c.get("commodity_hs", "")
        for c in state.corridor_metrics
        if c.get("origin_m49") == m49 and c.get("commodity_hs")
    })
    if not hs_codes:
        return {
            "m49": m49,
            "name": name,
            "pcc_proxy": True,
            "commodities": [],
        }

    net = build_exposure_network(state.corridor_metrics)
    rows = []
    for hs in hs_codes:
        pcc: dict[int, float] = {}
        for c in state.corridor_metrics:
            if (
                c.get("origin_m49") == m49
                and c.get("commodity_hs") == hs
                and c.get("destination_m49")
            ):
                pcc[int(c["destination_m49"])] = 1.0
        orps = net.compute_orps(m49, hs, pcc)
        rows.append({"commodity_hs": hs, "orps": orps})

    rows.sort(key=lambda r: r["orps"], reverse=True)
    return {
        "m49": m49,
        "name": name,
        "pcc_proxy": True,
        "commodities": rows,
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


@router.get("/{m49}/acep")
def get_country_acep(
    m49: int,
    state: AppState = Depends(get_state),
):
    """Compute ACEP (Attention Country Exposure Profile) for a destination.

    ACEP = sum(BDI * HIS * CRS) across all inbound corridors.
    Uses CRS=1.0 proxy until FAOSTAT data is integrated.
    """
    name = get_country_name(m49)
    net = build_exposure_network(state.corridor_metrics)

    # CRS=1.0 proxy: ACEP becomes sum(BDI * HIS) per inbound edge
    crs_proxy = {}
    for c in state.corridor_metrics:
        hs = c.get("commodity_hs", "")
        if hs:
            crs_proxy[hs] = 1.0

    acep = net.compute_acep(m49, crs_proxy)

    return {
        "m49": m49,
        "name": name or "Unknown",
        "acep": acep,
    }
