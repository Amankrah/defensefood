"""
Consumption Pipeline — Section 3 computation orchestration.

Computes the three blueprint demand-side metrics from FAOSTAT Food Balance
Sheets and population data:

  * **PCC** (Sec. 3.1, Eq. 10) — Per-capita apparent consumption (kg / capita / year)
        PCC(c, i, t) = D(c, i, t) / Pop(i, t)

  * **CRS** (Sec. 3.2, Eq. 11) — Commodity consumption rank within a country
        CRS(c, i, t) = 1 − (Rank(c, i, t) − 1) / (|C| − 1)
        where commodities are ordered by PCC descending; the most-consumed
        commodity scores 1.0 and the least 0.0.

  * **DIS** (Sec. 3.3, Eqs. 12-13) — Demand inelasticity
        CVD(c, i) = σ_PCC / μ_PCC  over a 5-year window
        DIS(c, i) = 1 − min(CVD, 1)
        Higher DIS = more stable demand = more fraud-exploitable.

All three are computed in one pass to share the per-capita time series. The
pipeline returns three lookups keyed by (hs, destination_m49) which the API
layer attaches to each corridor at startup.

Requires FAOSTAT FBS (multi-year domestic-supply quantity + population). When
the store is empty the pipeline returns three empty lookups and corridors
simply carry no consumption metrics; the CVS scorer then falls back to its
SCI+HIS-only path.
"""

from typing import Optional

import numpy as np

from defensefood.core import ConsumptionEngine
from defensefood.ingestion.faostat import FaostatStore


DIS_WINDOW_YEARS = 5  # blueprint Sec. 3.3 uses a 5-year window for CV


def _pcc_series(
    faostat: FaostatStore,
    hs: str,
    m49: int,
    target_year: int,
) -> list[float]:
    """Per-capita consumption time series ending at ``target_year``, length
    up to ``DIS_WINDOW_YEARS + 1`` (the target year plus the prior 5).
    Returns whatever years actually resolve; gaps drop out silently.
    """
    out: list[float] = []
    for yr in range(target_year - DIS_WINDOW_YEARS, target_year + 1):
        supply = faostat.domestic_supply.get((hs, m49, yr))
        pop = faostat.population_by_country.get((m49, yr))
        if supply is None or not pop or pop <= 0:
            continue
        pcc = ConsumptionEngine.compute_pcc(supply, pop)
        if pcc == pcc and pcc >= 0:  # NaN guard + sanity
            out.append(float(pcc))
    return out


def compute_consumption_lookups(
    faostat: Optional[FaostatStore],
    period: Optional[int] = None,
) -> tuple[
    dict[tuple[str, int], float],
    dict[tuple[str, int], float],
    dict[tuple[str, int], float],
]:
    """Build ``(pcc_lookup, crs_lookup, dis_lookup)``.

    Each lookup is keyed by ``(hs, destination_m49)`` -> float metric for the
    target year (latest FBS year by default, or the requested ``period`` if it
    exists in the store).

    Returns three empty dicts when no FAOSTAT supply data is loaded.
    """
    if faostat is None or not faostat.available or not faostat.domestic_supply:
        return {}, {}, {}

    years = {yr for (_hs, _m49, yr) in faostat.domestic_supply}
    if not years:
        return {}, {}, {}
    target_year = period if period in years else max(years)

    # ── 1. PCC for the target year, grouped by destination country ──
    # pcc_by_country[m49] = list of (hs, pcc) for ranking within that country
    pcc_by_country: dict[int, list[tuple[str, float]]] = {}
    pcc_lookup: dict[tuple[str, int], float] = {}

    for (hs, m49, yr), supply_kg in faostat.domestic_supply.items():
        if yr != target_year:
            continue
        pop = faostat.population_by_country.get((m49, yr))
        if not pop or pop <= 0:
            continue
        pcc = ConsumptionEngine.compute_pcc(supply_kg, pop)
        if pcc != pcc:  # NaN guard
            continue
        pcc_lookup[(hs, m49)] = float(pcc)
        pcc_by_country.setdefault(m49, []).append((hs, pcc))

    # ── 2. CRS — rank commodities within each country (descending PCC) ──
    crs_lookup: dict[tuple[str, int], float] = {}
    for m49, items in pcc_by_country.items():
        if not items:
            continue
        pcc_values = np.array([p for _hs, p in items], dtype=float)
        crs_values = ConsumptionEngine.compute_crs_batch(pcc_values)
        for (hs, _p), crs in zip(items, np.asarray(crs_values, dtype=float)):
            crs_lookup[(hs, m49)] = float(crs)

    # ── 3. DIS — coefficient of variation over the 5-year window ──
    # DIS needs ≥3 data points to be meaningful; we accept the engine's call.
    dis_lookup: dict[tuple[str, int], float] = {}
    for (hs, m49) in pcc_lookup.keys():
        series = _pcc_series(faostat, hs, m49, target_year)
        if len(series) < 3:
            continue
        try:
            dis = ConsumptionEngine.compute_dis(series)
        except Exception:  # noqa: BLE001 — defensively skip bad series
            continue
        if dis == dis and 0.0 <= dis <= 1.0:
            dis_lookup[(hs, m49)] = float(dis)

    return pcc_lookup, crs_lookup, dis_lookup


# ── Backwards-compatible shim ──────────────────────────────────────────────
# ``compute_crs_lookup`` was the only function exported before this rewrite;
# keep its signature so any external caller (or older test) still works.

def compute_crs_lookup(
    faostat: Optional[FaostatStore],
    period: Optional[int] = None,
) -> dict[tuple[str, int], float]:
    """Legacy entry point that returns CRS only. Prefer
    ``compute_consumption_lookups`` so PCC and DIS aren't recomputed twice.
    """
    _pcc, crs, _dis = compute_consumption_lookups(faostat, period)
    return crs
