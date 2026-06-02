"""Section 3 consumption — PCC, CRS, DIS coverage."""

import math

from defensefood.ingestion.faostat import FaostatStore
from defensefood.pipeline.consumption_pipeline import (
    DIS_WINDOW_YEARS,
    compute_consumption_lookups,
    compute_crs_lookup,
)


def _seed_store(years: list[int], hs_supply: dict[str, dict[int, float]], pop: float):
    """Build a FaostatStore with multi-year supply for the given HS codes.

    ``hs_supply[hs][year] = kg`` controls the per-year supply for one country
    (M49 = 56). Population is fixed across years.
    """
    store = FaostatStore(available=True)
    m49 = 56
    for hs, by_year in hs_supply.items():
        for yr, kg in by_year.items():
            store.domestic_supply[(hs, m49, yr)] = kg
    for yr in years:
        store.population_by_country[(m49, yr)] = pop
    return store, m49


# ── Empty / boundary cases ────────────────────────────────────────────────


def test_empty_store_yields_empty_lookups():
    pcc, crs, dis = compute_consumption_lookups(None)
    assert pcc == {} and crs == {} and dis == {}

    pcc, crs, dis = compute_consumption_lookups(FaostatStore(available=False))
    assert pcc == {} and crs == {} and dis == {}


def test_legacy_compute_crs_lookup_still_works():
    """Backwards-compat shim must keep the old single-return signature."""
    store, m49 = _seed_store(
        years=[2022],
        hs_supply={"1006": {2022: 10_000_000.0}},
        pop=1_000_000.0,
    )
    crs = compute_crs_lookup(store, 2022)
    # Single commodity has no peers to rank against — engine returns 1.0
    # (the sole commodity is by definition the top-consumed).
    assert math.isclose(crs[("1006", m49)], 1.0, rel_tol=1e-9)


# ── PCC ───────────────────────────────────────────────────────────────────


def test_pcc_is_supply_over_population():
    store, m49 = _seed_store(
        years=[2022],
        hs_supply={"1006": {2022: 12_000_000.0}},  # 12 kt
        pop=1_000_000.0,                            # 1M people
    )
    pcc, _crs, _dis = compute_consumption_lookups(store, 2022)
    # 12,000,000 kg / 1,000,000 people = 12 kg / capita / year
    assert math.isclose(pcc[("1006", m49)], 12.0, rel_tol=1e-9)


def test_pcc_skips_destinations_without_population():
    store = FaostatStore(available=True)
    store.domestic_supply[("1006", 999, 2022)] = 10_000.0
    pcc, crs, dis = compute_consumption_lookups(store, 2022)
    assert pcc == {} and crs == {} and dis == {}


# ── CRS ───────────────────────────────────────────────────────────────────


def test_crs_ranks_commodities_within_country():
    store, m49 = _seed_store(
        years=[2022],
        hs_supply={
            "1006": {2022: 40_000_000.0},  # highest PCC
            "1101": {2022: 20_000_000.0},  # middle
            "1107": {2022:  5_000_000.0},  # lowest
        },
        pop=1_000_000.0,
    )
    _pcc, crs, _dis = compute_consumption_lookups(store, 2022)
    assert crs[("1006", m49)] == 1.0     # highest-consumed -> 1.0
    assert crs[("1107", m49)] == 0.0     # lowest -> 0.0
    assert 0.0 < crs[("1101", m49)] < 1.0


# ── DIS ───────────────────────────────────────────────────────────────────


def test_dis_high_for_stable_demand():
    """A perfectly stable PCC series gives DIS = 1 (zero coefficient of variation)."""
    years = list(range(2017, 2023))  # 6 years
    store, m49 = _seed_store(
        years=years,
        hs_supply={"1006": {y: 10_000_000.0 for y in years}},  # constant kg
        pop=1_000_000.0,
    )
    _pcc, _crs, dis = compute_consumption_lookups(store, 2022)
    assert ("1006", m49) in dis
    assert math.isclose(dis[("1006", m49)], 1.0, rel_tol=1e-6)


def test_dis_low_for_volatile_demand():
    """A swing-y series produces DIS well below 1."""
    years = list(range(2017, 2023))
    # PCC values 5, 15, 5, 15, 5, 15 (kg/capita) — high relative variance
    supply = {y: (5e6 if (y % 2) else 15e6) for y in years}
    store, m49 = _seed_store(
        years=years,
        hs_supply={"1006": supply},
        pop=1_000_000.0,
    )
    _pcc, _crs, dis = compute_consumption_lookups(store, 2022)
    assert ("1006", m49) in dis
    assert dis[("1006", m49)] < 0.7   # volatile demand -> low inelasticity


def test_dis_requires_at_least_three_data_points():
    """Series shorter than 3 years is dropped from the DIS lookup."""
    years = [2021, 2022]  # only 2 years
    store, m49 = _seed_store(
        years=years,
        hs_supply={"1006": {2021: 10e6, 2022: 12e6}},
        pop=1_000_000.0,
    )
    pcc, _crs, dis = compute_consumption_lookups(store, 2022)
    # PCC for the target year still resolves, DIS doesn't.
    assert ("1006", m49) in pcc
    assert ("1006", m49) not in dis


def test_dis_uses_window_of_at_most_five_years_back():
    """Confirm only the 5-year window is sampled (older years are ignored)."""
    target = 2022
    # Years where PCC is volatile pre-window, but stable inside the window.
    volatile_pre = {2010: 1e6, 2011: 50e6, 2012: 1e6}   # ignored (older than window)
    stable_in   = {2018: 10e6, 2019: 10e6, 2020: 10e6, 2021: 10e6, 2022: 10e6}
    supply = {**volatile_pre, **stable_in}
    store, m49 = _seed_store(
        years=list(supply.keys()),
        hs_supply={"1006": supply},
        pop=1_000_000.0,
    )
    _pcc, _crs, dis = compute_consumption_lookups(store, target)
    # If we only sample (target - 5 ... target), CV is zero and DIS = 1.
    assert math.isclose(dis[("1006", m49)], 1.0, rel_tol=1e-6)
    # Sanity: blueprint says 5-year window.
    assert DIS_WINDOW_YEARS == 5
