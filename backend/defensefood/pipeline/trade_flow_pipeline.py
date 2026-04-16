"""
Trade Flow Pipeline -- Section 5 computation orchestration.

Computes unit value anomalies, volume anomalies, mirror trade discrepancies,
and concentration shifts from Comtrade data through the Rust engine.
"""

import numpy as np
import pandas as pd

from defensefood.core import DependencyEngine, TradeFlowEngine


def compute_unit_value_anomalies(
    trade_df: pd.DataFrame,
    commodity_hs: str,
    destination_m49: int,
    period: int,
) -> pd.DataFrame:
    """Compute unit value z-scores for all origins of a commodity to a destination.

    Returns DataFrame with columns: partner_code, unit_value, z_uv.
    """
    mask = (
        (trade_df["cmdCode"].astype(str) == str(commodity_hs))
        & (trade_df["reporterCode"].astype(int) == destination_m49)
        & (trade_df["period"].astype(int) == period)
        & (trade_df["flowCode"].astype(str) == "M")
    )
    imports = trade_df[mask].copy()

    if imports.empty:
        return pd.DataFrame(columns=["partnerCode", "unit_value", "z_uv"])

    # Group by partner to get total value and weight
    grouped = imports.groupby("partnerCode").agg(
        value=("primaryValue", "sum"),
        weight=("netWgt", "sum"),
    ).reset_index()

    values = grouped["value"].values.astype(float)
    weights = grouped["weight"].values.astype(float)

    zscores = TradeFlowEngine.unit_value_zscores(
        np.array(values), np.array(weights)
    )

    grouped["unit_value"] = np.where(weights > 0, values / weights, np.nan)
    grouped["z_uv"] = zscores

    return grouped[["partnerCode", "unit_value", "z_uv"]]


def compute_mirror_discrepancy(
    trade_df: pd.DataFrame,
    commodity_hs: str,
    importer_m49: int,
    exporter_m49: int,
    period: int,
) -> float:
    """Compute Mirror Trade Discrepancy (Eq. 27) from both sides of trade.

    M_i = what importer reports importing from exporter.
    X_j = what exporter reports exporting to importer.
    """
    # What importer reports
    m_mask = (
        (trade_df["cmdCode"].astype(str) == str(commodity_hs))
        & (trade_df["reporterCode"].astype(int) == importer_m49)
        & (trade_df["partnerCode"].astype(int) == exporter_m49)
        & (trade_df["period"].astype(int) == period)
        & (trade_df["flowCode"].astype(str) == "M")
    )
    m_reported = trade_df.loc[m_mask, "netWgt"].sum()

    # What exporter reports
    x_mask = (
        (trade_df["cmdCode"].astype(str) == str(commodity_hs))
        & (trade_df["reporterCode"].astype(int) == exporter_m49)
        & (trade_df["partnerCode"].astype(int) == importer_m49)
        & (trade_df["period"].astype(int) == period)
        & (trade_df["flowCode"].astype(str) == "X")
    )
    x_reported = trade_df.loc[x_mask, "netWgt"].sum()

    return TradeFlowEngine.mirror_discrepancy(m_reported, x_reported)


def compute_concentration_shifts(
    trade_df: pd.DataFrame,
    commodity_hs: str,
    reporter_m49: int,
    period_current: int,
    period_previous: int,
) -> dict:
    """Compute HHI and OCS shifts between two periods (Eq. 28-29)."""
    from defensefood.pipeline.dependency_pipeline import compute_hhi_for_reporter

    hhi_current = compute_hhi_for_reporter(trade_df, commodity_hs, reporter_m49, period_current)
    hhi_previous = compute_hhi_for_reporter(trade_df, commodity_hs, reporter_m49, period_previous)

    return {
        "hhi_current": hhi_current,
        "hhi_previous": hhi_previous,
        "delta_hhi": TradeFlowEngine.delta_hhi(hhi_current, hhi_previous),
    }
