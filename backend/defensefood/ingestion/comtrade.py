"""
UN Comtrade API client.

Refactored from backend/script/comtrade_fetcher.py.
Fetches bilateral trade data for commodity-country pairs.
"""

import os
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://comtradeapi.un.org/data/v1/get"
SUBSCRIPTION_KEY = os.getenv("COMTRADE_SUBSCRIPTION_KEY", "")

DEFAULT_HEADERS = {
    "Cache-Control": "no-cache",
    "Ocp-Apim-Subscription-Key": SUBSCRIPTION_KEY,
}

# Columns of interest from Comtrade response
TRADE_COLUMNS = [
    "period", "reporterCode", "reporterDesc", "partnerCode", "partnerDesc",
    "cmdCode", "cmdDesc", "flowCode", "flowDesc",
    "primaryValue", "netWgt", "qty", "qtyUnitAbbr",
]


def fetch_trade_data(
    reporter_code: str,
    partner_code: str = "",
    cmd_code: str = "",
    flow_code: str = "M",
    period: str = "",
    type_code: str = "C",
    freq_code: str = "A",
    cl_code: str = "HS",
    max_records: int = 500,
    include_desc: bool = True,
) -> dict:
    """Fetch raw trade data from UN Comtrade API.

    Returns the JSON response as a dict.
    """
    url = f"{BASE_URL}/{type_code}/{freq_code}/{cl_code}"
    params = {
        "reporterCode": reporter_code,
        "cmdCode": cmd_code,
        "flowCode": flow_code,
        "partnerCode": partner_code,
        "period": period,
        "maxRecords": max_records,
        "includeDesc": str(include_desc).lower(),
    }
    params = {k: v for k, v in params.items() if v}

    response = requests.get(url, headers=DEFAULT_HEADERS, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def response_to_dataframe(response: dict) -> pd.DataFrame:
    """Convert Comtrade API JSON response to a pandas DataFrame."""
    data = response.get("data", [])
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)


def extract_trade_values(df: pd.DataFrame) -> pd.DataFrame:
    """Select the standard trade columns from a Comtrade DataFrame."""
    available = [c for c in TRADE_COLUMNS if c in df.columns]
    return df[available].copy()


def fetch_bilateral_trade(
    reporter_code: str,
    partner_code: str,
    hs_codes: list[str],
    years: list[int],
    flow_code: str = "M",
    delay: float = 1.0,
) -> pd.DataFrame:
    """Fetch bilateral trade data for specific country pair, HS codes, and years.

    Returns a combined DataFrame for all HS codes and years.
    """
    all_dfs = []

    for year in years:
        cmd_str = ",".join(hs_codes)
        try:
            response = fetch_trade_data(
                reporter_code=reporter_code,
                partner_code=partner_code,
                cmd_code=cmd_str,
                flow_code=flow_code,
                period=str(year),
            )
            df = response_to_dataframe(response)
            if not df.empty:
                df = extract_trade_values(df)
                all_dfs.append(df)
        except requests.RequestException as e:
            print(f"  Warning: API error for {reporter_code}->{partner_code} {year}: {e}")

        if delay > 0:
            time.sleep(delay)

    if not all_dfs:
        return pd.DataFrame()
    return pd.concat(all_dfs, ignore_index=True)


def load_merged_trade_data(path: Optional[Path] = None) -> pd.DataFrame:
    """Load the pre-merged trade CSV from the output directory."""
    if path is None:
        path = (
            Path(__file__).resolve().parent.parent.parent
            / "script" / "output" / "merged_trade_data.csv"
        )
    if not path.exists():
        raise FileNotFoundError(f"Merged trade CSV not found: {path}")
    return pd.read_csv(path)
