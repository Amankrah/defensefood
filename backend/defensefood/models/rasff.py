"""Pydantic models for RASFF notification data."""

from enum import Enum

from pydantic import BaseModel


class HazardCategory(str, Enum):
    BIOLOGICAL = "biological"
    CHEM_PESTICIDES = "chem_pesticides"
    CHEM_HEAVY_METALS = "chem_heavy_metals"
    CHEM_MYCOTOXINS = "chem_mycotoxins"
    CHEM_OTHER = "chem_other"
    REGULATORY = "regulatory"


class ClassificationType(str, Enum):
    ALERT = "alert_notification"
    BORDER_REJECTION = "border_rejection"
    INFO_FOLLOW_UP = "info_follow_up"
    INFO_ATTENTION = "info_attention"


class RiskLevel(str, Enum):
    SERIOUS = "serious"
    POTENTIALLY_SERIOUS = "potentially_serious"
    POTENTIAL_RISK = "potential_risk"
    NOT_SERIOUS = "not_serious"


class RasffNotificationModel(BaseModel):
    """API representation of a RASFF notification."""
    reference: str
    commodity_hs: str
    commodity_name: str = ""
    origin_country: str
    origin_m49: int
    affected_countries: list[int]
    classification: ClassificationType
    risk_decision: RiskLevel
    hazard_category: HazardCategory
    period: int
    severity_weight: float = 0.0


class RasffIngestionSummary(BaseModel):
    """Summary of RASFF data ingestion."""
    total_notifications: int
    total_corridors: int
    unique_origins: int
    unique_destinations: int
    unique_commodities: int
    unmapped_origins: list[str] = []
    unmapped_destinations: list[str] = []
    notifications_without_origin: int = 0
    notifications_without_destination: int = 0
    self_trade_pairs_skipped: int = 0
