"""
Consumption Pipeline -- Section 3 computation orchestration.

Computes per-capita consumption (PCC = food-use supply / population) for each
(commodity, country) from FAOSTAT Food Balance Sheets, then ranks commodities
within each country into the Commodity Consumption Rank Score (CRS, Eq. 11).

CRS attaches to a corridor via its DESTINATION country: how central the
commodity is to that country's diet drives the consumption-side vulnerability.

Requires FAOSTAT FBS data. When the store is empty the pipeline returns an empty
lookup and corridors simply carry no `crs` (CVS then falls back to SCI+HIS).
"""

from typing import Optional

import numpy as np

from defensefood.core import ConsumptionEngine
from defensefood.ingestion.faostat import FaostatStore


def compute_crs_lookup(
    faostat: Optional[FaostatStore],
    period: Optional[int] = None,
) -> dict[tuple[str, int], float]:
    """Build a {(hs, destination_m49): crs} lookup from FBS supply + population.

    For each country, commodities are ranked by PCC (descending) and scored with
    Eq. 11 so the most-consumed commodity scores 1.0 and the least 0.0.
    """
    if faostat is None or not faostat.available or not faostat.domestic_supply:
        return {}

    # Determine the period to score on (latest year present in FBS supply keys).
    years = {yr for (_hs, _m49, yr) in faostat.domestic_supply}
    if not years:
        return {}
    target_year = period if period in years else max(years)

    # Build PCC per (hs, country) for the target year.
    # pcc_by_country[m49] = list of (hs, pcc)
    pcc_by_country: dict[int, list[tuple[str, float]]] = {}
    for (hs, m49, yr), supply_kg in faostat.domestic_supply.items():
        if yr != target_year:
            continue
        pop = faostat.population(m49, yr)
        if not pop or pop <= 0:
            continue
        pcc = ConsumptionEngine.compute_pcc(supply_kg, pop)
        if pcc != pcc:  # NaN guard
            continue
        pcc_by_country.setdefault(m49, []).append((hs, pcc))

    lookup: dict[tuple[str, int], float] = {}
    for m49, items in pcc_by_country.items():
        if not items:
            continue
        pcc_values = np.array([p for _hs, p in items], dtype=float)
        crs_values = ConsumptionEngine.compute_crs_batch(pcc_values)
        for (hs, _p), crs in zip(items, np.asarray(crs_values, dtype=float)):
            lookup[(hs, m49)] = float(crs)

    return lookup
