"""
UN Comtrade Data Fetching Scripts

This module provides tools for fetching bilateral trade data
from the UN Comtrade API.

Modules:
    - comtrade_fetcher: Core API fetch functions
    - hs_codes_loader: Load HS codes from commodities CSV
    - country_loader: Load country pairs from RASFF Excel
    - fetch_comtrade_pipeline: Main pipeline script
"""

from .comtrade_fetcher import (
    fetch_trade_data,
    response_to_dataframe,
    extract_trade_values,
    fetch_bilateral_trade,
    fetch_batch,
    save_to_csv,
    save_to_json,
)

from .hs_codes_loader import (
    load_commodities_data,
    get_unique_hs_codes,
    get_hs_codes_with_names,
)

from .country_loader import (
    get_m49_code,
    get_trade_pairs_with_hs_codes,
    get_unique_country_pairs,
    extract_trade_pairs,
    M49_COUNTRY_CODES,
)

__all__ = [
    # Fetcher
    "fetch_trade_data",
    "response_to_dataframe",
    "extract_trade_values",
    "fetch_bilateral_trade",
    "fetch_batch",
    "save_to_csv",
    "save_to_json",
    # HS Codes
    "load_commodities_data",
    "get_unique_hs_codes",
    "get_hs_codes_with_names",
    # Country Loader
    "get_m49_code",
    "get_trade_pairs_with_hs_codes",
    "get_unique_country_pairs",
    "extract_trade_pairs",
    "M49_COUNTRY_CODES",
]
