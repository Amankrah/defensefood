"""Pydantic models for trade data and corridor metrics."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FlowCode(str, Enum):
    IMPORT = "M"
    EXPORT = "X"


class TradeObservation(BaseModel):
    """A single trade observation from UN Comtrade."""
    period: int
    reporter_code: int
    reporter_name: str
    partner_code: int
    partner_name: str
    commodity_hs: str
    commodity_desc: str = ""
    flow_code: FlowCode = FlowCode.IMPORT
    value_usd: float = 0.0
    net_weight_kg: float = 0.0
    quantity: float = 0.0
    quantity_unit: str = ""


class DependencyMetrics(BaseModel):
    """Section 2 dependency metrics for a corridor."""
    ds_prime: float = Field(description="Apparent domestic supply (Eq. 2)")
    idr: float = Field(description="Import Dependency Ratio (Eq. 3)")
    ocs: float = Field(description="Origin Country Share (Eq. 4)")
    bdi: float = Field(description="Bilateral Dependency Index (Eq. 5)")
    hhi: float = Field(description="Herfindahl-Hirschman Index (Eq. 7)")
    ssr: float = Field(description="Self-Sufficiency Ratio (Eq. 8)")
    sci: float = Field(description="Supply Criticality Index (Eq. 9)")
    sci_norm: float = Field(description="Normalised SCI [0,1]")


class ConsumptionMetrics(BaseModel):
    """Section 3 consumption metrics for a commodity-country pair."""
    pcc: float = Field(description="Per Capita Apparent Consumption (Eq. 10)")
    crs: float = Field(description="Commodity Consumption Rank Score (Eq. 11)")
    dis: float = Field(description="Demand Inelasticity Score (Eq. 13)")


class HazardMetrics(BaseModel):
    """Section 4 hazard signal metrics for a corridor."""
    his: float = Field(description="Hazard Intensity Score (Eq. 15)")
    hdi: float = Field(description="Hazard Diversity Index normalised (Eq. 18)")
    dgi: float = Field(description="Detection Gap Indicator (Eq. 19)")
    notification_count: int = 0
    severity_weighted_count: float = 0.0


class TradeFlowMetrics(BaseModel):
    """Section 5 trade flow anomaly metrics for a corridor."""
    unit_value: float = Field(description="USD/kg (Eq. 20)")
    z_uv: float = Field(description="Unit value z-score (Eq. 23)")
    z_volume: float = Field(description="Volume anomaly z-score (Eq. 26)")
    mtd: float = Field(description="Mirror Trade Discrepancy (Eq. 27)")
    delta_hhi: Optional[float] = Field(None, description="HHI shift (Eq. 28)")
    delta_ocs: Optional[float] = Field(None, description="OCS shift (Eq. 29)")


class CorridorProfile(BaseModel):
    """Full profile of a trade corridor (c, i, j)."""
    commodity_hs: str
    commodity_name: str = ""
    destination_m49: int
    destination_name: str = ""
    origin_m49: int
    origin_name: str = ""
    period: int

    dependency: Optional[DependencyMetrics] = None
    consumption: Optional[ConsumptionMetrics] = None
    hazard: Optional[HazardMetrics] = None
    trade_flow: Optional[TradeFlowMetrics] = None
    composite_score: Optional[float] = None


class CorridorRanking(BaseModel):
    """A corridor with its composite vulnerability score for ranked listings."""
    commodity_hs: str
    commodity_name: str = ""
    destination_m49: int
    destination_name: str = ""
    origin_m49: int
    origin_name: str = ""
    cvs: float = Field(description="Composite Vulnerability Score")
    sci_norm: float = 0.0
    his_norm: float = 0.0
    crs_norm: float = 0.0
