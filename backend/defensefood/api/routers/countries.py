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
    """Origin Risk Propagation Score (Sec. 6.2) per commodity for this origin.

    Uses real per-capita consumption (PCC) from the Section 3 lookup whenever
    available; falls back to 1.0 only for (commodity, destination) pairs
    FAOSTAT doesn't cover. ``pcc_proxy`` flags lanes where the fallback fired.
    """
    from defensefood.ingestion.hs_codes import normalize_hs

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
    proxy_used_any = False
    for hs in hs_codes:
        hs_norm = normalize_hs(hs)
        pcc: dict[int, float] = {}
        pcc_real = 0
        pcc_proxy = 0
        for c in state.corridor_metrics:
            if (
                c.get("origin_m49") == m49
                and c.get("commodity_hs") == hs
                and c.get("destination_m49")
            ):
                dest = int(c["destination_m49"])
                real = state.pcc_lookup.get((hs_norm, dest)) if hs_norm else None
                if real is not None:
                    pcc[dest] = real
                    pcc_real += 1
                else:
                    pcc[dest] = 1.0
                    pcc_proxy += 1
                    proxy_used_any = True
        orps = net.compute_orps(m49, hs, pcc)
        orps_by_role = net.compute_orps_by_role(m49, hs, pcc)
        rows.append({
            "commodity_hs": hs,
            "orps": orps,
            "orps_by_role": orps_by_role,
            "pcc_real_count": pcc_real,
            "pcc_proxy_count": pcc_proxy,
        })

    rows.sort(key=lambda r: r["orps"], reverse=True)
    return {
        "m49": m49,
        "name": name,
        "pcc_proxy": proxy_used_any,
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

    ACEP = sum(BDI * HIS * CRS) across all inbound corridors (Sec. 6.3 Eq. 34).

    CRS comes from the Section 3 lookup (state.crs_lookup) keyed by
    (normalized_hs, destination_m49). HS codes without a CRS value contribute
    0 (rather than the prior 1.0 proxy, which silently inflated ACEP).

    Surfaces ``crs_missing_hs`` and ``crs_resolved_hs`` so the dashboard can
    show how many commodities backed the score.
    """
    from defensefood.ingestion.hs_codes import normalize_hs
    from defensefood.pipeline.network_pipeline import count_missing_bdi_edges

    name = get_country_name(m49)
    net = build_exposure_network(state.corridor_metrics)

    # Build the CRS map for this destination from the cached lookup; track
    # which HS codes resolved versus had to fall back to 0.
    crs_by_commodity: dict[str, float] = {}
    resolved: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()
    for c in state.corridor_metrics:
        if c.get("destination_m49") != m49:
            continue
        hs = c.get("commodity_hs") or ""
        if not hs or hs in seen:
            continue
        seen.add(hs)
        hs_norm = normalize_hs(hs)
        crs = state.crs_lookup.get((hs_norm, m49))
        if crs is not None:
            crs_by_commodity[hs] = float(crs)
            resolved.append(hs)
        else:
            crs_by_commodity[hs] = 0.0
            missing.append(hs)

    acep = net.compute_acep(m49, crs_by_commodity)
    acep_by_role = net.compute_acep_by_role(m49, crs_by_commodity)

    # Diagnostic: how many inbound corridors had no BDI? Those contribute 0
    # under the new Slice-B math; we surface the count so users can tell.
    bdi_missing = count_missing_bdi_edges(
        state.corridor_metrics, destination_m49=m49
    )

    return {
        "m49": m49,
        "name": name or "Unknown",
        # acep === acep_by_role["confirmed"] — kept as the top-level
        # planner-facing number; Slice A's role split lives alongside it.
        "acep": acep,
        "acep_by_role": acep_by_role,
        "crs_resolved_count": len(resolved),
        "crs_missing_count": len(missing),
        # Cap the missing list so the response stays small; the count is
        # authoritative.
        "crs_missing_hs": sorted(missing)[:10],
        "bdi_missing_inbound": bdi_missing,
    }
