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
    origin_m49: int | None = None,
) -> dict:
    """Compute HHI and (optionally) OCS shifts between two periods.

    Blueprint Eq. 28 (ΔHHI) is destination-level; Eq. 29 (ΔOCS) is per-origin
    and only computed when ``origin_m49`` is given. Both are simple period-
    over-period subtractions:
        ΔHHI = HHI(c, i, t) − HHI(c, i, t-1)
        ΔOCS = OCS(c, i, j, t) − OCS(c, i, j, t-1)
    where OCS(j) = M(j) / M(*) for the destination's imports.
    """
    from defensefood.ingestion.hs_codes import normalize_hs
    from defensefood.pipeline.dependency_pipeline import compute_hhi_for_reporter

    hhi_current = compute_hhi_for_reporter(trade_df, commodity_hs, reporter_m49, period_current)
    hhi_previous = compute_hhi_for_reporter(trade_df, commodity_hs, reporter_m49, period_previous)

    out: dict = {
        "hhi_current": hhi_current,
        "hhi_previous": hhi_previous,
        "delta_hhi": TradeFlowEngine.delta_hhi(hhi_current, hhi_previous),
    }

    if origin_m49 is None:
        return out

    # Per-origin OCS shift (Eq. 29).
    hs_norm = normalize_hs(commodity_hs)
    if hs_norm is None:
        out["ocs_current"] = float("nan")
        out["ocs_previous"] = float("nan")
        out["delta_ocs"] = float("nan")
        return out

    def _ocs(period: int) -> float:
        cmd = trade_df["cmdCode"].map(normalize_hs)
        mask = (
            cmd.fillna("").astype(str).str.startswith(hs_norm)
            & (trade_df["reporterCode"].astype(int) == reporter_m49)
            & (trade_df["period"].astype(int) == period)
            & (trade_df["flowCode"].astype(str) == "M")
        )
        rows = trade_df[mask]
        if rows.empty:
            return float("nan")
        wgt = pd.to_numeric(rows["netWgt"], errors="coerce").fillna(0.0)
        total = float(wgt.sum())
        if total <= 0:
            return float("nan")
        bilateral_mask = mask & (trade_df["partnerCode"].astype(int) == origin_m49)
        bilateral = float(
            pd.to_numeric(trade_df.loc[bilateral_mask, "netWgt"], errors="coerce").fillna(0.0).sum()
        )
        return bilateral / total

    ocs_current = _ocs(period_current)
    ocs_previous = _ocs(period_previous)
    out["ocs_current"] = ocs_current
    out["ocs_previous"] = ocs_previous
    if ocs_current != ocs_current or ocs_previous != ocs_previous:  # NaN guard
        out["delta_ocs"] = float("nan")
    else:
        out["delta_ocs"] = TradeFlowEngine.delta_ocs(ocs_current, ocs_previous)
    return out


# ── 5.2 Volume Anomaly Detection (Eq. 24-26) ───────────────────────────────


def _corridor_quantity_series(
    trade_df: pd.DataFrame,
    commodity_hs: str,
    destination_m49: int,
    origin_m49: int,
) -> list[float]:
    """Return the (period-ordered) import-quantity time series for one corridor.

    Used by the Volume Anomaly z-score: the engine wants a chronologically
    ordered list of M(c, i, j, τ) values; the last element is the current
    period being scored, the prior k elements are the rolling-window history.
    """
    from defensefood.ingestion.hs_codes import normalize_hs

    hs_norm = normalize_hs(commodity_hs)
    if hs_norm is None:
        return []
    cmd = trade_df["cmdCode"].map(normalize_hs)
    mask = (
        cmd.fillna("").astype(str).str.startswith(hs_norm)
        & (trade_df["reporterCode"].astype(int) == destination_m49)
        & (trade_df["partnerCode"].astype(int) == origin_m49)
        & (trade_df["flowCode"].astype(str) == "M")
    )
    rows = trade_df[mask]
    if rows.empty:
        return []
    by_period = (
        rows.groupby(rows["period"].astype(int))["netWgt"]
        .sum()
        .sort_index()
    )
    return [float(v) for v in by_period.values]


def compute_volume_anomaly_for_corridor(
    trade_df: pd.DataFrame,
    commodity_hs: str,
    destination_m49: int,
    origin_m49: int,
    window_k: int = 5,
) -> tuple[float, int]:
    """Rolling-window z-score on the corridor's own import history.

    Returns ``(z, n_points)``:
      * ``z`` — float z-score for the latest period, NaN if the series is
        shorter than ``window_k + 1`` points.
      * ``n_points`` — number of time periods we found (the caller can render
        a "needs more history" empty state when this is < window_k + 1).
    """
    series = _corridor_quantity_series(
        trade_df, commodity_hs, destination_m49, origin_m49
    )
    z = TradeFlowEngine.volume_anomaly(series, window_k) if series else float("nan")
    return z, len(series)
