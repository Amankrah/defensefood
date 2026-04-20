"""Hazard and RASFF data endpoints."""

from fastapi import APIRouter, Depends

from defensefood.api.dependencies import AppState, get_state

router = APIRouter(prefix="/hazards", tags=["hazards"])


@router.get("/summary")
def get_rasff_summary(state: AppState = Depends(get_state)):
    """Get summary of loaded RASFF data."""
    s = state.rasff_summary
    if not s:
        return {"error": "No RASFF data loaded"}
    return {
        "total_notifications": s.total_notifications,
        "total_corridors": s.total_corridors,
        "active_corridors": s.active_corridors,
        "unique_origins": s.unique_origins,
        "unique_destinations": s.unique_destinations,
        "unique_commodities": s.unique_commodities,
        "unmapped_origins": s.unmapped_origins,
        "unmapped_destinations": s.unmapped_destinations,
        "notifications_without_origin": s.notifications_without_origin,
        "notifications_without_destination": s.notifications_without_destination,
        "self_trade_pairs_skipped": s.self_trade_pairs_skipped,
        "role_counts": s.role_counts,
        "notification_objects_built": len(state.notifications),
        "current_period": state.current_period,
    }


@router.get("/types")
def get_hazard_types():
    """List the 6 hazard type categories."""
    return {
        "hazard_types": [
            {"index": 0, "id": "biological", "label": "Biological"},
            {"index": 1, "id": "chem_pesticides", "label": "Chemical - Pesticides"},
            {"index": 2, "id": "chem_heavy_metals", "label": "Chemical - Heavy Metals"},
            {"index": 3, "id": "chem_mycotoxins", "label": "Chemical - Mycotoxins"},
            {"index": 4, "id": "chem_other", "label": "Chemical - Other"},
            {"index": 5, "id": "regulatory", "label": "Regulatory"},
        ]
    }
