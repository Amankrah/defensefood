"""FAOSTAT bulk loader: empty fallback, unit conversion, CPC->HS join."""

import pandas as pd

from defensefood.ingestion.faostat import load_faostat_store


def test_empty_dir_returns_unavailable(tmp_path):
    store = load_faostat_store(tmp_path)
    assert store.available is False
    assert store.production == {}


def _write_bulk(tmp_path):
    prod = pd.DataFrame({
        "Area Code (M49)": ["'056", "'620"],
        "Item Code (CPC)": ["'04330", "'01123"],
        "Element": ["Production", "Production"],
        "Year": [2022, 2022],
        "Unit": ["t", "t"],
        "Value": [10.0, 500.0],
    })
    prod.to_csv(tmp_path / "Production_Crops_Livestock_E_All_Data.csv", index=False)
    fbs = pd.DataFrame({
        "Area Code (M49)": ["'620", "'620"],
        "Item Code": [2807, 2807],
        "Item Code (FBS)": ["'S2807", "'S2807"],
        "Item": ["Rice and products", "Rice and products"],
        "Element": ["Domestic supply quantity", "Total Population - Both sexes"],
        "Year": [2022, 2022],
        "Unit": ["1000 t", "1000 No"],
        "Value": [2.0, 10000.0],
    })
    fbs.to_csv(tmp_path / "FoodBalanceSheets_E_All_Data.csv", index=False)


def test_bulk_parse_units_and_join(tmp_path):
    _write_bulk(tmp_path)
    store = load_faostat_store(tmp_path)
    assert store.available is True
    # CPC 04330 -> HS 030731 (mussels), 10 t -> 10_000 kg
    assert store.production_kg("030731", 56, 2022) == 10_000.0
    # CPC 01123 -> rice HS 100630, 500 t -> 500_000 kg
    assert store.production_kg("100630", 620, 2022) == 500_000.0
    # FBS domestic supply 2 (1000 t) -> 2_000_000 kg
    assert store.domestic_supply_kg("100630", 620, 2022) == 2_000_000.0
    # population 10000 (1000 persons) -> 10_000_000
    assert store.population(620, 2022) == 10_000_000.0


def test_missing_columns_does_not_crash(tmp_path):
    bad = pd.DataFrame({"foo": [1], "bar": [2]})
    bad.to_csv(tmp_path / "production_garbage.csv", index=False)
    store = load_faostat_store(tmp_path)
    # File is unusable but loader must not raise; store stays empty/unavailable.
    assert store.production == {}
