"""Pydantic models for scoring configuration and results."""

from enum import Enum

from pydantic import BaseModel, Field


class NormalisationMethod(str, Enum):
    MIN_MAX = "min_max"
    PERCENTILE_RANK = "percentile_rank"
    LOG_PERCENTILE = "log_percentile"


class CompositionMethod(str, Enum):
    WEIGHTED_LINEAR = "weighted_linear"
    GEOMETRIC_MEAN = "geometric_mean"
    HYBRID = "hybrid"


class ScoringConfig(BaseModel):
    """Configuration for composite vulnerability scoring."""
    normalisation_method: NormalisationMethod = NormalisationMethod.PERCENTILE_RANK
    composition_method: CompositionMethod = CompositionMethod.HYBRID
    alpha_decay: float = Field(0.90, ge=0.01, le=0.99, description="HIS temporal decay")
    w_hazard: float = Field(1.0, ge=0.0, description="Hazard signal weight")
    w_price: float = Field(1.0, ge=0.0, description="Price anomaly weight")
    w_supply_chain: float = Field(1.0, ge=0.0, description="Supply chain complexity weight")


class CountryExposure(BaseModel):
    """ACEP result for a country."""
    country_m49: int
    country_name: str = ""
    acep: float = Field(description="Attention Country Exposure Profile (Eq. 34)")
    top_commodities: list[str] = []
    top_origins: list[int] = []


class OriginRisk(BaseModel):
    """ORPS result for an origin country."""
    origin_m49: int
    origin_name: str = ""
    commodity_hs: str
    orps: float = Field(description="Origin Risk Propagation Score (Eq. 33)")
