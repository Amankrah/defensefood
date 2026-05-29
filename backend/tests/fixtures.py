"""Shared synthetic data builders for the test suite."""

import pandas as pd

from defensefood.ingestion.faostat import FaostatStore

# Belgium-flaxseed worked example (PDF p.9), expressed in kg.
#   P = 500, M = 12000 (8000+2000+1500+500), X = 1500  =>  DS' = 11000
#   IDR = 12000/11000 = 1.0909
#   OCS (bilateral 8000) = 0.6667
#   HHI over [8000,2000,1500,500] = 0.4896
#   SCI = 1.0833, SCI_norm = 0.5417
WORKED_HS = "120740"
WORKED_DEST = 56      # Belgium
WORKED_ORIGIN = 251   # France (the 8000 partner)
WORKED_PERIOD = 2022
WORKED_PRODUCTION_KG = 500.0


def worked_example_trade_df() -> pd.DataFrame:
    rows = [
        # imports into Belgium of HS 120740 from four origins
        (WORKED_PERIOD, WORKED_DEST, 251, WORKED_HS, "M", 8000.0),
        (WORKED_PERIOD, WORKED_DEST, 276, WORKED_HS, "M", 2000.0),
        (WORKED_PERIOD, WORKED_DEST, 528, WORKED_HS, "M", 1500.0),
        (WORKED_PERIOD, WORKED_DEST, 380, WORKED_HS, "M", 500.0),
        # Belgium's exports of the same commodity
        (WORKED_PERIOD, WORKED_DEST, 251, WORKED_HS, "X", 1500.0),
    ]
    return pd.DataFrame(
        rows,
        columns=["period", "reporterCode", "partnerCode", "cmdCode", "flowCode", "netWgt"],
    )


def synthetic_faostat_store() -> FaostatStore:
    """A small FAOSTAT store keyed on the worked-example HS/country."""
    store = FaostatStore(available=True)
    store.production[(WORKED_HS, WORKED_DEST, WORKED_PERIOD)] = WORKED_PRODUCTION_KG
    store.domestic_supply[(WORKED_HS, WORKED_DEST, WORKED_PERIOD)] = 9000.0
    store.population_by_country[(WORKED_DEST, WORKED_PERIOD)] = 11_000_000.0
    return store
