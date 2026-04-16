"""
Dependency Pipeline -- Section 2 computation orchestration.

Loads trade data, aggregates by corridor, and computes dependency metrics
(IDR, OCS, BDI, HHI, SSR, SCI) through the Rust engine.
"""

import numpy as np
import pandas as pd

from defensefood.core import DependencyEngine
from defensefood.ingestion.comtrade import load_merged_trade_data


def compute_corridor_dependency(
    trade_df: pd.DataFrame,
    commodity_hs: str,
    destination_m49: int,
    origin_m49: int,
    period: int,
    production_kg: float = 0.0,
) -> dict:
    """Compute all Section 2 metrics for a single corridor.

    Args:
        trade_df: DataFrame with Comtrade trade data.
        commodity_hs: HS commodity code.
        destination_m49: Importing country M49 code.
        origin_m49: Exporting country M49 code.
        period: Year.
        production_kg: Domestic production (from FAOSTAT). 0 if unavailable.

    Returns:
        Dict of dependency metrics or error.
    """
    # Filter to this commodity, destination, period (imports)
    mask = (
        (trade_df["cmdCode"].astype(str) == str(commodity_hs))
        & (trade_df["reporterCode"].astype(int) == destination_m49)
        & (trade_df["period"].astype(int) == period)
        & (trade_df["flowCode"].astype(str) == "M")
    )
    imports = trade_df[mask]

    # Total imports from all origins
    total_imports_kg = imports["netWgt"].sum()

    # Bilateral import from this origin
    bilateral_mask = imports["partnerCode"].astype(int) == origin_m49
    bilateral_import_kg = imports.loc[bilateral_mask, "netWgt"].sum()

    # Exports (for domestic supply balance)
    export_mask = (
        (trade_df["cmdCode"].astype(str) == str(commodity_hs))
        & (trade_df["reporterCode"].astype(int) == destination_m49)
        & (trade_df["period"].astype(int) == period)
        & (trade_df["flowCode"].astype(str) == "X")
    )
    total_exports_kg = trade_df.loc[export_mask, "netWgt"].sum()

    # All origin import quantities (for HHI computation)
    origin_imports = (
        imports.groupby("partnerCode")["netWgt"]
        .sum()
        .values
        .astype(float)
    )
    all_origin_imports = np.array(origin_imports) if len(origin_imports) > 0 else None

    return DependencyEngine.compute_all(
        production_kg=production_kg,
        total_imports_kg=total_imports_kg,
        total_exports_kg=total_exports_kg,
        bilateral_import_kg=bilateral_import_kg,
        all_origin_imports=all_origin_imports,
    )


def compute_hhi_for_reporter(
    trade_df: pd.DataFrame,
    commodity_hs: str,
    reporter_m49: int,
    period: int,
) -> float:
    """Compute HHI for a reporter's imports of a commodity in a period."""
    mask = (
        (trade_df["cmdCode"].astype(str) == str(commodity_hs))
        & (trade_df["reporterCode"].astype(int) == reporter_m49)
        & (trade_df["period"].astype(int) == period)
        & (trade_df["flowCode"].astype(str) == "M")
    )
    imports = trade_df[mask]
    if imports.empty:
        return float("nan")

    origin_totals = imports.groupby("partnerCode")["netWgt"].sum()
    total = origin_totals.sum()
    if total <= 0:
        return float("nan")

    shares = (origin_totals / total).values.astype(float)
    return DependencyEngine.compute_hhi(np.array(shares))
