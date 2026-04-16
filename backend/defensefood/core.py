"""
Thin Python wrapper over the defensefood_core Rust extension.

Provides a Pythonic interface and handles DataFrame <-> Rust type conversion.
Pipeline code imports from here, not directly from defensefood_core.
"""

from typing import Optional

import numpy as np
import pandas as pd

import defensefood_core
from defensefood_core import (
    Classification,
    HazardType,
    RasffNotification,
    RiskDecision,
    TradeRecord,
)
from defensefood_core import consumption, dependency, hazard, network, scoring, trade_flow


# ---------------------------------------------------------------------------
#  Section 2: Commodity Dependency Models
# ---------------------------------------------------------------------------

class DependencyEngine:
    """Compute dependency metrics for a corridor (c, i, j, t)."""

    @staticmethod
    def compute_all(
        production_kg: float,
        total_imports_kg: float,
        total_exports_kg: float,
        bilateral_import_kg: float,
        domestic_supply_kg: Optional[float] = None,
        all_origin_imports: Optional[np.ndarray] = None,
    ) -> dict:
        """Compute all Section 2 metrics for a single corridor.

        Returns dict with keys: ds_prime, idr, ocs, bdi, ssr, hhi, sci, sci_norm.
        Returns error key if DS' <= 0 (data quality issue).
        """
        ds = dependency.compute_supply_balance(
            production_kg, total_imports_kg, total_exports_kg
        )
        if np.isnan(ds):
            return {"error": "DS' <= 0, data quality issue (flag and exclude)"}

        idr = dependency.compute_idr(total_imports_kg, ds)
        ocs = dependency.compute_ocs(bilateral_import_kg, total_imports_kg)
        bdi = dependency.compute_bdi(bilateral_import_kg, ds)
        ssr = dependency.compute_ssr(production_kg, domestic_supply_kg or ds)

        hhi = float("nan")
        if all_origin_imports is not None:
            shares = dependency.compute_ocs_shares(all_origin_imports)
            hhi = dependency.compute_hhi(shares)

        sci = dependency.compute_sci(idr, ocs, hhi) if not np.isnan(hhi) else float("nan")
        sci_norm = sci / 2.0 if not np.isnan(sci) else float("nan")

        return {
            "ds_prime": ds,
            "idr": idr,
            "ocs": ocs,
            "bdi": bdi,
            "ssr": ssr,
            "hhi": hhi,
            "sci": sci,
            "sci_norm": sci_norm,
        }

    @staticmethod
    def compute_hhi(shares: np.ndarray) -> float:
        return dependency.compute_hhi(shares)

    @staticmethod
    def compute_sci(idr: float, ocs: float, hhi: float) -> float:
        return dependency.compute_sci(idr, ocs, hhi)


# ---------------------------------------------------------------------------
#  Section 3: Consumption Demand Modelling
# ---------------------------------------------------------------------------

class ConsumptionEngine:
    """Compute consumption and demand metrics."""

    @staticmethod
    def compute_pcc(domestic_supply_kg: float, population: float) -> float:
        return consumption.compute_pcc(domestic_supply_kg, population)

    @staticmethod
    def compute_crs_batch(pcc_values: np.ndarray) -> np.ndarray:
        return consumption.compute_crs_batch(pcc_values)

    @staticmethod
    def compute_dis(pcc_series: list[float]) -> float:
        return consumption.compute_dis(pcc_series)

    @staticmethod
    def compute_cv(pcc_series: list[float]) -> float:
        return consumption.compute_cv(pcc_series)


# ---------------------------------------------------------------------------
#  Section 4: Hazard Signal Modelling
# ---------------------------------------------------------------------------

CLASSIFICATION_MAP = {
    "alert notification": Classification.AlertNotification,
    "alert": Classification.AlertNotification,
    "border rejection": Classification.BorderRejection,
    "border rejection notification": Classification.BorderRejection,
    "information for follow-up": Classification.InfoFollowUp,
    "information notification for follow-up": Classification.InfoFollowUp,
    "information for attention": Classification.InfoAttention,
    "information notification for attention": Classification.InfoAttention,
}

RISK_DECISION_MAP = {
    "serious": RiskDecision.Serious,
    "potentially serious": RiskDecision.PotentiallySerious,
    "potential risk": RiskDecision.PotentialRisk,
    "not serious": RiskDecision.NotSerious,
    "undecided": RiskDecision.PotentialRisk,  # Conservative default
}

HAZARD_TYPE_MAP = {
    "biological": HazardType.Biological,
    "pathogenic micro-organisms": HazardType.Biological,
    "parasitic infestation": HazardType.Biological,
    "pesticide residues": HazardType.ChemPesticides,
    "heavy metals": HazardType.ChemHeavyMetals,
    "mycotoxins": HazardType.ChemMycotoxins,
    "chemical contamination": HazardType.ChemOther,
    "food additives and flavourings": HazardType.ChemOther,
    "migration": HazardType.ChemOther,
    "composition": HazardType.Regulatory,
    "labelling absent/incomplete/incorrect": HazardType.Regulatory,
    "adulteration/fraud": HazardType.Regulatory,
    "foreign bodies": HazardType.ChemOther,
    "allergens": HazardType.ChemOther,
    "novel food": HazardType.Regulatory,
    "non-pathogenic micro-organisms": HazardType.Biological,
    "gmo / novel food": HazardType.Regulatory,
    "radiation": HazardType.ChemOther,
    "other hazard": HazardType.ChemOther,
}


def parse_classification(value: str) -> Classification:
    """Map RASFF classification string to Rust enum."""
    if not value or pd.isna(value):
        return Classification.InfoAttention
    return CLASSIFICATION_MAP.get(str(value).strip().lower(), Classification.InfoAttention)


def parse_risk_decision(value: str) -> RiskDecision:
    """Map RASFF risk decision string to Rust enum."""
    if not value or pd.isna(value):
        return RiskDecision.PotentialRisk
    return RISK_DECISION_MAP.get(str(value).strip().lower(), RiskDecision.PotentialRisk)


def parse_hazard_type(value: str) -> HazardType:
    """Map RASFF hazard category string to Rust enum."""
    if not value or pd.isna(value):
        return HazardType.ChemOther
    val_lower = str(value).strip().lower()
    for key, ht in HAZARD_TYPE_MAP.items():
        if key in val_lower:
            return ht
    return HazardType.ChemOther


class HazardEngine:
    """Compute hazard signal metrics from RASFF data."""

    @staticmethod
    def severity(classification: Classification, risk_decision: RiskDecision) -> float:
        return hazard.compute_severity(classification, risk_decision)

    @staticmethod
    def compute_his(
        notifications: list[RasffNotification],
        commodity_hs: str,
        dest_m49: int,
        origin_m49: int,
        current_period: int,
        alpha: float = 0.90,
    ) -> float:
        return hazard.compute_his(
            notifications, commodity_hs, dest_m49, origin_m49, current_period, alpha
        )

    @staticmethod
    def compute_hdi(hazard_type_counts: list[float]) -> float:
        return hazard.compute_hdi(hazard_type_counts)

    @staticmethod
    def compute_dgi(trade_share: float, notification_share: float) -> float:
        return hazard.compute_dgi(trade_share, notification_share)

    @staticmethod
    def compute_dgi_from_counts(
        bilateral_import: float,
        total_import: float,
        bilateral_notifications: float,
        total_notifications: float,
    ) -> float:
        return hazard.compute_dgi_from_counts(
            bilateral_import, total_import, bilateral_notifications, total_notifications
        )

    @staticmethod
    def df_to_notifications(df: pd.DataFrame) -> list[RasffNotification]:
        """Convert a RASFF DataFrame to a list of Rust RasffNotification objects.

        Expected DataFrame columns:
            reference, origin, for_followUp, hs_code, commodities,
            classification, risk_decision, hazard_category, period
        """
        from defensefood.ingestion.countries import get_m49_code

        notifications = []
        for _, row in df.iterrows():
            origin = str(row.get("origin", "")).strip()
            origin_m49 = get_m49_code(origin)
            if origin_m49 is None:
                continue

            follow_up = row.get("for_followUp", "")
            if pd.isna(follow_up) or not follow_up:
                continue

            affected = []
            for country in str(follow_up).split(","):
                c = country.strip()
                code = get_m49_code(c)
                if code is not None:
                    affected.append(code)
            if not affected:
                continue

            hs_code = row.get("hs_code", "")
            if pd.isna(hs_code) or not hs_code:
                continue
            try:
                hs_str = str(int(float(hs_code)))
            except (ValueError, TypeError):
                hs_str = str(hs_code).strip()

            period = int(row.get("period", 0))
            if period == 0:
                continue

            notif = RasffNotification(
                reference=str(row.get("reference", "")),
                commodity_hs=hs_str,
                origin_m49=origin_m49,
                affected_countries=affected,
                classification=parse_classification(row.get("classification", "")),
                risk_decision=parse_risk_decision(row.get("risk_decision", "")),
                hazard_type=parse_hazard_type(row.get("hazard_category", "")),
                period=period,
            )
            notifications.append(notif)

        return notifications


# ---------------------------------------------------------------------------
#  Section 5: Trade Flow Analysis
# ---------------------------------------------------------------------------

class TradeFlowEngine:
    """Compute trade flow anomaly metrics."""

    @staticmethod
    def unit_value(value_usd: float, quantity_kg: float) -> float:
        return trade_flow.compute_unit_value(value_usd, quantity_kg)

    @staticmethod
    def unit_value_zscores(values: np.ndarray, quantities: np.ndarray) -> np.ndarray:
        return trade_flow.compute_unit_value_zscore_batch(values, quantities)

    @staticmethod
    def volume_anomaly(series: list[float], window_k: int = 5) -> float:
        return trade_flow.compute_volume_anomaly(series, window_k)

    @staticmethod
    def mirror_discrepancy(m_reported: float, x_reported: float) -> float:
        return trade_flow.compute_mtd(m_reported, x_reported)

    @staticmethod
    def delta_hhi(hhi_current: float, hhi_previous: float) -> float:
        return trade_flow.compute_delta_hhi(hhi_current, hhi_previous)

    @staticmethod
    def delta_ocs(ocs_current: float, ocs_previous: float) -> float:
        return trade_flow.compute_delta_ocs(ocs_current, ocs_previous)


# ---------------------------------------------------------------------------
#  Section 6: Network Model
# ---------------------------------------------------------------------------

class NetworkEngine:
    """Build and query the exposure network."""

    def __init__(self):
        self._network = network.ExposureNetwork()

    @property
    def raw(self) -> network.ExposureNetwork:
        return self._network

    def add_edge(
        self,
        origin_m49: int,
        dest_m49: int,
        commodity_hs: str,
        trade_weight: float,
        hazard_weight: float,
        dep_weight: float,
    ):
        self._network.add_trade_edge(
            origin_m49, dest_m49, commodity_hs,
            trade_weight, hazard_weight, dep_weight,
        )

    def compute_orps(
        self,
        origin_m49: int,
        commodity_hs: str,
        pcc_values: dict[int, float],
    ) -> float:
        return network.compute_orps(self._network, origin_m49, commodity_hs, pcc_values)

    def compute_acep(
        self,
        destination_m49: int,
        crs_by_commodity: dict[str, float],
    ) -> float:
        return network.compute_acep(self._network, destination_m49, crs_by_commodity)

    @property
    def node_count(self) -> int:
        return self._network.node_count()

    @property
    def edge_count(self) -> int:
        return self._network.edge_count()


# ---------------------------------------------------------------------------
#  Section 7: Composite Vulnerability Scoring
# ---------------------------------------------------------------------------

class ScoringEngine:
    """Normalise and compose vulnerability scores."""

    METHODS = ("min_max", "percentile_rank", "log_percentile")

    @staticmethod
    def normalise(values: np.ndarray, method: str = "percentile_rank") -> np.ndarray:
        if method == "min_max":
            return scoring.normalise_min_max(values)
        elif method == "percentile_rank":
            return scoring.normalise_percentile_rank(values)
        elif method == "log_percentile":
            return scoring.normalise_log_percentile(values)
        raise ValueError(f"Unknown normalisation method: {method}")

    @staticmethod
    def weighted_linear(normalised_values: list[float], weights: list[float]) -> float:
        return scoring.score_weighted_linear(normalised_values, weights)

    @staticmethod
    def geometric_mean(normalised_values: list[float], weights: list[float]) -> float:
        return scoring.score_geometric_mean(normalised_values, weights)

    @staticmethod
    def hybrid(
        sci_norm: float,
        crs_norm: float,
        his_norm: float = 0.0,
        pas_norm: float = 0.0,
        sccs_norm: float = 0.0,
        w_h: float = 1.0,
        w_p: float = 1.0,
        w_sc: float = 1.0,
    ) -> float:
        return scoring.score_hybrid(
            sci_norm, crs_norm, his_norm, pas_norm, sccs_norm, w_h, w_p, w_sc
        )

    @staticmethod
    def equal_weights(k: int) -> list[float]:
        return scoring.equal_weights(k)
