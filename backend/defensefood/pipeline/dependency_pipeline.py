"""
Dependency Pipeline -- Section 2 computation orchestration.

Aggregates trade data by corridor and computes dependency metrics (IDR, OCS,
BDI, HHI, SSR, SCI) through the Rust engine. Production (P) and domestic supply
(D) come from FAOSTAT when available; otherwise DS' falls back to the trade-only
proxy (DS' = M - X) and the result is tagged ``provenance = "trade_only"``.

HS rollup: when a corridor's HS code is present in trade at the same
granularity (exact match), the aggregators use only those exact rows. When
the corridor HS has no exact-match rows but child codes (longer prefixes)
do, the aggregator sums across the children. This avoids double-counting
when Comtrade publishes both a 4-digit parent aggregate and its 6-digit
breakdowns for the same reporter — exact match wins; the prefix fallback
only fires for corridor codes that aren't published at their stated level.

Two entry points:
  * ``compute_corridor_dependency``  -- one corridor, used by on-demand routes.
  * ``run_dependency_pipeline``      -- batch enrichment for every corridor at
    startup, with trade aggregates pre-computed once.
"""

from typing import Iterable, Optional

import numpy as np
import pandas as pd

from defensefood_core import dependency as _dep
from defensefood.core import DependencyEngine
from defensefood.ingestion.faostat import FaostatStore
from defensefood.ingestion.hs_codes import normalize_hs


def _annotate(result: dict, production_kg: float, provenance: str) -> dict:
    """Attach provenance + interpretive flags to a raw metric dict."""
    if "error" in result:
        return result
    result["provenance"] = provenance
    result["production_kg"] = production_kg
    idr = result.get("idr")
    # IDR > 1 means imports exceed apparent domestic supply: a re-export / trade-hub
    # signal under the full balance sheet, but usually just a zero-production
    # artefact in trade-only mode. Flag it either way; the UI decides framing.
    result["idr_gt_1"] = bool(idr is not None and not np.isnan(idr) and idr > 1.0)
    return result


def _hs_match_mask(cmd_series: pd.Series, hs: str) -> pd.Series:
    """Boolean mask of trade rows for this corridor HS.

    Prefers exact-HS match; only falls back to children (prefix rollup) when
    the corridor's exact HS has no rows in the data. Comtrade often publishes
    both a 4-digit parent and its 6-digit children for the same reporter, so a
    naive prefix match would double-count. The two-stage rule keeps existing
    exact-match behaviour and only adds the prefix rollup as a fallback for
    corridor codes that aren't present in trade at their stated granularity.
    """
    cmd = cmd_series.fillna("").astype(str)
    exact = cmd == hs
    if exact.any():
        return exact
    return cmd.str.startswith(hs) & (cmd != hs)


def compute_corridor_dependency(
    trade_df: pd.DataFrame,
    commodity_hs: str,
    destination_m49: int,
    origin_m49: int,
    period: int,
    production_kg: float = 0.0,
    domestic_supply_kg: Optional[float] = None,
    delta_stocks_kg: float = 0.0,
    provenance: str = "trade_only",
) -> dict:
    """Compute all Section 2 metrics for a single corridor.

    Args:
        trade_df: Comtrade trade data.
        commodity_hs: HS commodity code (any granularity; normalised internally,
            and rolled up so child trade rows are included).
        destination_m49: Importing country M49 (Comtrade reporter).
        origin_m49: Exporting country M49 (Comtrade partner).
        period: Year.
        production_kg: Domestic production (FAOSTAT). 0 when unavailable.
        domestic_supply_kg: FAOSTAT food-use supply D for SSR; defaults to DS'.
        delta_stocks_kg: Stock change ΔS for the full DS' (Eq. 1).
        provenance: "faostat" or "trade_only".
    """
    hs = normalize_hs(commodity_hs)
    if hs is None:
        return {"error": "Unrecognised commodity HS code"}
    cmd = trade_df["cmdCode"].map(normalize_hs)
    period_i = trade_df["period"].astype(int)
    flow = trade_df["flowCode"].astype(str)
    wgt = pd.to_numeric(trade_df["netWgt"], errors="coerce").fillna(0.0)

    hs_mask = _hs_match_mask(cmd, hs)

    imp_mask = hs_mask & (period_i == period) & (flow == "M") & (
        trade_df["reporterCode"].astype(int) == destination_m49
    )
    imports = trade_df[imp_mask]
    total_imports_kg = float(wgt[imp_mask].sum())

    bilateral_mask = imp_mask & (trade_df["partnerCode"].astype(int) == origin_m49)
    bilateral_import_kg = float(wgt[bilateral_mask].sum())

    export_mask = hs_mask & (period_i == period) & (flow == "X") & (
        trade_df["reporterCode"].astype(int) == destination_m49
    )
    total_exports_kg = float(wgt[export_mask].sum())

    if not imports.empty:
        origin_imports = (
            wgt[imp_mask]
            .groupby(imports["partnerCode"].astype(int))
            .sum()
            .values.astype(float)
        )
        all_origin_imports = np.array(origin_imports)
    else:
        all_origin_imports = None

    result = DependencyEngine.compute_all(
        production_kg=production_kg,
        total_imports_kg=total_imports_kg,
        total_exports_kg=total_exports_kg,
        bilateral_import_kg=bilateral_import_kg,
        domestic_supply_kg=domestic_supply_kg,
        all_origin_imports=all_origin_imports,
        delta_stocks_kg=delta_stocks_kg,
    )
    result = _annotate(result, production_kg, provenance)
    if "error" not in result:
        result["bilateral_import_kg"] = bilateral_import_kg
        result["total_imports_kg"] = total_imports_kg
    return result


class TradeAggregates:
    """Pre-aggregated import/export quantities indexed by exact HS, with
    prefix-rollup helpers used by the batch dependency pipeline.

    Built once per (period) so batch dependency avoids re-scanning the trade
    frame for every corridor. Per-exact-HS dicts are preserved for any
    downstream consumer; the new ``lookup_rollup`` method sums across every
    exact HS code that begins with a given corridor HS so 4-digit RASFF
    lanes pick up the 6-digit Comtrade rows that sit underneath them.
    """

    def __init__(self, trade_df: pd.DataFrame, period: int):
        self.period = period
        df = trade_df.copy()
        df["hs"] = df["cmdCode"].map(normalize_hs)
        df["wgt"] = pd.to_numeric(df["netWgt"], errors="coerce").fillna(0.0)
        df = df[df["period"].astype(int) == period]
        df = df[df["hs"].notna()]
        df["reporter"] = df["reporterCode"].astype(int)
        df["partner"] = df["partnerCode"].astype(int)
        flow = df["flowCode"].astype(str)

        imp = df[flow == "M"]
        exp = df[flow == "X"]

        # Per-exact-HS aggregates. Other code may inspect these directly, so
        # we keep the shapes the previous version exposed.
        self.imports_total: dict[tuple[str, int], float] = (
            imp.groupby(["hs", "reporter"])["wgt"].sum().to_dict()
        )
        self.exports_total: dict[tuple[str, int], float] = (
            exp.groupby(["hs", "reporter"])["wgt"].sum().to_dict()
        )
        self.imports_bilateral: dict[tuple[str, int, int], float] = (
            imp.groupby(["hs", "reporter", "partner"])["wgt"].sum().to_dict()
        )

        # Partner breakdown keyed by (hs, reporter) -> {partner: weight}.
        # Used by lookup_rollup so HHI can be recomputed across child HS codes
        # without re-scanning the full bilateral dict.
        self._partners_for_hs_reporter: dict[tuple[str, int], dict[int, float]] = {}
        for (hs, reporter, partner), wgt in self.imports_bilateral.items():
            self._partners_for_hs_reporter.setdefault((hs, reporter), {})[partner] = wgt

        # Sorted list of every exact HS in the period, plus a per-prefix cache
        # so a 4-digit lookup doesn't re-scan the list for every corridor.
        self._all_exact_hs: list[str] = sorted(
            {hs for (hs, _) in self.imports_total.keys()}
            | {hs for (hs, _) in self.exports_total.keys()}
        )
        self._matching_cache: dict[str, tuple[str, ...]] = {}

    def _matching(self, prefix: str) -> tuple[str, ...]:
        cached = self._matching_cache.get(prefix)
        if cached is not None:
            return cached
        result = tuple(h for h in self._all_exact_hs if h.startswith(prefix))
        self._matching_cache[prefix] = result
        return result

    def lookup_rollup(
        self, hs: str, reporter: int, origin: int
    ) -> tuple[float, float, float, float]:
        """Return (total_imports, total_exports, bilateral, hhi) for the lane.

        Comtrade often reports both a 4-digit parent aggregate (e.g. ``1006``)
        AND its 6-digit children (``100610/20/30``) for the same reporter, so
        we cannot blindly sum the prefix family — that would double-count.
        Rule: prefer exact-HS data when the (hs, reporter) pair has any rows
        in the period; fall back to summing children only when no exact-HS row
        exists. HHI is recomputed from the partner shares of whichever
        granularity actually drove the totals.
        """
        # Exact-HS presence check: any import/export/bilateral row at this granularity?
        exact_present = (
            (hs, reporter) in self._partners_for_hs_reporter
            or (hs, reporter) in self.imports_total
            or (hs, reporter) in self.exports_total
        )

        if exact_present:
            total_imports = self.imports_total.get((hs, reporter), 0.0)
            total_exports = self.exports_total.get((hs, reporter), 0.0)
            bilateral = self.imports_bilateral.get((hs, reporter, origin), 0.0)
            partner_totals = dict(self._partners_for_hs_reporter.get((hs, reporter), {}))
        else:
            # No exact row — try children only (skip ``hs`` itself; it's already absent).
            children = [h for h in self._matching(hs) if h != hs]
            if not children:
                return 0.0, 0.0, 0.0, float("nan")
            total_imports = 0.0
            total_exports = 0.0
            bilateral = 0.0
            partner_totals: dict[int, float] = {}
            for h in children:
                total_imports += self.imports_total.get((h, reporter), 0.0)
                total_exports += self.exports_total.get((h, reporter), 0.0)
                bilateral += self.imports_bilateral.get((h, reporter, origin), 0.0)
                for p, w in self._partners_for_hs_reporter.get((h, reporter), {}).items():
                    partner_totals[p] = partner_totals.get(p, 0.0) + w

        hhi = float("nan")
        if partner_totals:
            total = sum(partner_totals.values())
            if total > 0:
                shares = np.array(
                    [w / total for w in partner_totals.values()], dtype=float
                )
                hhi = DependencyEngine.compute_hhi(shares)

        return total_imports, total_exports, bilateral, hhi


def run_dependency_pipeline(
    trade_df: pd.DataFrame,
    corridor_keys: Iterable[tuple[str, int, int]],
    faostat: Optional[FaostatStore] = None,
    period: Optional[int] = None,
) -> dict[tuple[str, int, int], dict]:
    """Batch-compute Section 2 metrics for many corridors.

    Args:
        trade_df: Comtrade trade data (all periods).
        corridor_keys: iterable of (commodity_hs, destination_m49, origin_m49).
        faostat: FAOSTAT store for P/D; None or empty -> trade-only DS'.
        period: trade year to use; defaults to the latest year in trade_df.

    Returns:
        Dict keyed by the ORIGINAL (commodity_hs, dest, origin) tuple ->
        metric dict (with provenance / flags). Corridors with no trade and no
        production yield ``{"error": ...}`` and should be left unscored.
    """
    if trade_df is None or trade_df.empty:
        return {}

    if period is None:
        period = int(sorted(trade_df["period"].astype(int).unique())[-1])

    agg = TradeAggregates(trade_df, period)
    has_faostat = faostat is not None and faostat.available

    out: dict[tuple[str, int, int], dict] = {}
    for key in corridor_keys:
        commodity_hs, dest, origin = key
        hs = normalize_hs(commodity_hs)
        if hs is None:
            continue

        total_imports, total_exports, bilateral, hhi = agg.lookup_rollup(
            hs, dest, origin
        )

        production_kg = 0.0
        domestic_supply_kg = None
        delta_stocks_kg = 0.0
        provenance = "trade_only"
        if has_faostat:
            p = faostat.production_kg(hs, dest, period)
            d = faostat.domestic_supply_kg(hs, dest, period)
            s = faostat.stock_variation_kg(hs, dest, period)
            if p is not None:
                production_kg = p
            if d is not None:
                domestic_supply_kg = d
            if s is not None:
                delta_stocks_kg = s
            if p is not None or d is not None:
                provenance = "faostat"

        # Skip corridors with no trade footprint and no production -> nothing to compute.
        if total_imports <= 0 and bilateral <= 0 and production_kg <= 0 and total_exports <= 0:
            continue

        result = DependencyEngine.compute_all(
            production_kg=production_kg,
            total_imports_kg=total_imports,
            total_exports_kg=total_exports,
            bilateral_import_kg=bilateral,
            domestic_supply_kg=domestic_supply_kg,
            all_origin_imports=None,  # HHI supplied directly below (rolled-up)
            delta_stocks_kg=delta_stocks_kg,
        )
        if "error" in result:
            out[key] = result
            continue

        # Inject the rolled-up reporter HHI and recompute SCI with it.
        result["hhi"] = hhi
        if not np.isnan(hhi):
            result["sci"] = DependencyEngine.compute_sci(result["idr"], result["ocs"], hhi)
            result["sci_norm"] = _dep.compute_sci_normalised(
                result["idr"], result["ocs"], hhi
            )
        result = _annotate(result, production_kg, provenance)
        result["bilateral_import_kg"] = bilateral
        result["total_imports_kg"] = total_imports
        out[key] = result

    return out


def compute_hhi_for_reporter(
    trade_df: pd.DataFrame,
    commodity_hs: str,
    reporter_m49: int,
    period: int,
) -> float:
    """Compute HHI for a reporter's imports of a commodity in a period.

    Rolls trade rows up: any cmdCode that starts with the corridor HS counts.
    """
    hs = normalize_hs(commodity_hs)
    if hs is None:
        return float("nan")
    cmd = trade_df["cmdCode"].map(normalize_hs)
    mask = (
        _hs_match_mask(cmd, hs)
        & (trade_df["reporterCode"].astype(int) == reporter_m49)
        & (trade_df["period"].astype(int) == period)
        & (trade_df["flowCode"].astype(str) == "M")
    )
    imports = trade_df[mask]
    if imports.empty:
        return float("nan")

    wgt = pd.to_numeric(imports["netWgt"], errors="coerce").fillna(0.0)
    origin_totals = wgt.groupby(imports["partnerCode"].astype(int)).sum()
    total = origin_totals.sum()
    if total <= 0:
        return float("nan")

    shares = (origin_totals / total).values.astype(float)
    return DependencyEngine.compute_hhi(np.array(shares))
