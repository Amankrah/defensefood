"""Section 3 consumption: CRS ranking from FAOSTAT FBS supply/population."""

from defensefood.ingestion.faostat import FaostatStore
from defensefood.pipeline.consumption_pipeline import compute_crs_lookup


def test_empty_store_yields_no_crs():
    assert compute_crs_lookup(None) == {}
    assert compute_crs_lookup(FaostatStore(available=False)) == {}


def test_crs_ranks_commodities_within_country():
    store = FaostatStore(available=True)
    m49, yr, pop = 56, 2022, 1_000_000.0
    # Three commodities with different per-capita supply.
    store.domestic_supply[("1006", m49, yr)] = 40_000_000.0  # highest PCC
    store.domestic_supply[("1101", m49, yr)] = 20_000_000.0  # middle
    store.domestic_supply[("1107", m49, yr)] = 5_000_000.0   # lowest
    store.population_by_country[(m49, yr)] = pop

    crs = compute_crs_lookup(store, yr)
    # Highest-consumed -> 1.0, lowest -> 0.0
    assert crs[("1006", m49)] == 1.0
    assert crs[("1107", m49)] == 0.0
    assert 0.0 < crs[("1101", m49)] < 1.0


def test_crs_skips_country_without_population():
    store = FaostatStore(available=True)
    store.domestic_supply[("1006", 999, 2022)] = 10_000.0
    # no population entry for area 999
    assert compute_crs_lookup(store, 2022) == {}
