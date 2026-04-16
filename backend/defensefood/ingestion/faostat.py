"""
FAOSTAT / Eurostat data ingestion.

Provides production (P), domestic supply (D), and population data
needed for dependency (Section 2) and consumption (Section 3) models.

NOTE: This is a stub. FAOSTAT API integration and local CSV loading
will be implemented when data sources are available.
"""

from typing import Optional

import pandas as pd


def load_production_data(path: Optional[str] = None) -> pd.DataFrame:
    """Load FAOSTAT production data.

    Expected columns: commodity_hs, country_m49, period,
    production_kg, domestic_supply_kg, population.

    TODO: Implement FAOSTAT API client or CSV loader when data is available.
    """
    if path:
        return pd.read_csv(path)
    return pd.DataFrame(columns=[
        "commodity_hs", "country_m49", "period",
        "production_kg", "domestic_supply_kg", "population",
    ])


def load_food_balance_sheets(path: Optional[str] = None) -> pd.DataFrame:
    """Load FAOSTAT Food Balance Sheets.

    Provides D(c,i,t) = domestic supply for food use, and
    population data Pop(i,t) needed for PCC calculation.

    TODO: Implement when FAOSTAT data source is configured.
    """
    if path:
        return pd.read_csv(path)
    return pd.DataFrame(columns=[
        "commodity_hs", "country_m49", "period",
        "domestic_supply_food_kg", "population",
    ])
