"""
UN Comtrade API - Data Fetcher
Endpoint: getDa (Trade Data)
Docs: https://uncomtrade.org/docs/subscriptions/

Fetches trade quantity and trade value between two countries.
"""

import os
import requests
import json
import time
import pandas as pd
from typing import Optional, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────

SUBSCRIPTION_KEY = os.getenv("COMTRADE_SUBSCRIPTION_KEY", "1da582ac898f4f2bab671c90a019411c")

BASE_URL = "https://comtradeapi.un.org/data/v1/get"

DEFAULT_HEADERS = {
    "Cache-Control": "no-cache",
    "Ocp-Apim-Subscription-Key": SUBSCRIPTION_KEY,
}


# ─────────────────────────────────────────────
#  CORE FETCH FUNCTION
# ─────────────────────────────────────────────

def fetch_trade_data(
    type_code: str = "C",           # "C" = commodities, "S" = services
    freq_code: str = "A",           # "A" = annual, "M" = monthly
    cl_code: str = "HS",            # Classification: HS, SITC, BEC, EBOPS
    reporter_code: Optional[str] = None,    # M49 country codes, comma-separated
    cmd_code: Optional[str] = None,         # Commodity code (e.g. "0101" for horses)
    flow_code: Optional[str] = None,        # "X" = export, "M" = import
    partner_code: Optional[str] = None,     # Partner country M49 code
    period: Optional[str] = None,           # Year (2023) or month (202301)
    published_date_from: Optional[str] = None,
    published_date_to: Optional[str] = None,
    max_records: int = 500,
    include_desc: bool = True,
) -> dict:
    """
    Fetch trade data from UN Comtrade getDa endpoint.

    Returns the raw JSON response as a dict.
    """

    # Build URL path: /getDa/{typeCode}/{freqCode}/{clCode}
    url = f"{BASE_URL}/{type_code}/{freq_code}/{cl_code}"

    # Build optional query parameters
    params = {}
    if reporter_code:       params["reporterCode"]      = reporter_code
    if cmd_code:            params["cmdCode"]            = cmd_code
    if flow_code:           params["flowCode"]           = flow_code
    if partner_code:        params["partnerCode"]        = partner_code
    if period:              params["period"]             = period
    if published_date_from: params["publishedDateFrom"]  = published_date_from
    if published_date_to:   params["publishedDateTo"]    = published_date_to
    if max_records:         params["maxRecords"]         = max_records
    if include_desc:        params["includeDesc"]        = "true"

    print(f"-> Requesting: {url}")
    print(f"   Params: {params}")

    try:
        response = requests.get(url, headers=DEFAULT_HEADERS, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.HTTPError as e:
        print(f"[HTTP Error] {e.response.status_code}: {e.response.text}")
        raise
    except requests.exceptions.Timeout:
        print("[Error] Request timed out.")
        raise
    except requests.exceptions.RequestException as e:
        print(f"[Error] {e}")
        raise


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def response_to_dataframe(response: dict) -> pd.DataFrame:
    """Convert the API response data list to a Pandas DataFrame."""
    data = response.get("data", [])
    if not data:
        print("[Warning] No data returned.")
        return pd.DataFrame()
    return pd.DataFrame(data)


def extract_trade_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract the key trade columns we care about:
    - period: Year/Month of trade
    - reporterDesc: Reporting country name
    - partnerDesc: Partner country name
    - cmdCode: HS commodity code
    - cmdDesc: Commodity description
    - flowDesc: Import/Export
    - primaryValue: Trade value in USD
    - netWgt: Net weight in kg
    - qty: Quantity
    - qtyUnitAbbr: Unit for qty
    """
    if df.empty:
        return df

    columns_of_interest = [
        "period",
        "reporterCode",
        "reporterDesc",
        "partnerCode",
        "partnerDesc",
        "cmdCode",
        "cmdDesc",
        "flowCode",
        "flowDesc",
        "primaryValue",  # Trade value in USD
        "netWgt",        # Net weight in kg
        "qty",           # Quantity
        "qtyUnitAbbr"    # Unit
    ]

    # Only select columns that exist in the dataframe
    available_cols = [col for col in columns_of_interest if col in df.columns]
    return df[available_cols]


def save_to_json(response: dict, filename: str = "comtrade_output.json"):
    """Save raw response to JSON file."""
    with open(filename, "w") as f:
        json.dump(response, f, indent=2)
    print(f"[OK] Saved JSON to {filename}")


def save_to_csv(df: pd.DataFrame, filename: str = "comtrade_output.csv"):
    """Save DataFrame to CSV file."""
    df.to_csv(filename, index=False)
    print(f"[OK] Saved CSV to {filename}")


# ─────────────────────────────────────────────
#  BILATERAL TRADE FETCHER
# ─────────────────────────────────────────────

def fetch_bilateral_trade(
    reporter_code: str,
    partner_code: str,
    hs_codes: List[str],
    periods: List[str],
    flow_code: str = "X",  # "M" = imports, "X" = exports, "MX" = both
    delay_seconds: float = 1.0,
) -> pd.DataFrame:
    """
    Fetch bilateral trade data between two countries for specific HS codes.

    Args:
        reporter_code: M49 code of reporting country
        partner_code: M49 code of partner country
        hs_codes: List of HS commodity codes
        periods: List of years (e.g., ["2021", "2022", "2023"])
        flow_code: "M" = imports, "X" = exports, "MX" = both (makes separate calls)
        delay_seconds: Pause between API calls (rate limiting)

    Returns:
        DataFrame with trade data containing trade_qty and trade_value
    """
    all_frames = []

    # Handle "MX" by making separate calls for imports and exports
    flow_codes = ["M", "X"] if flow_code == "MX" else [flow_code]

    for hs_code in hs_codes:
        for period in periods:
            for fc in flow_codes:
                print(f"\n-- HS Code: {hs_code} | Period: {period} | Flow: {fc}")
                try:
                    raw = fetch_trade_data(
                        type_code="C",
                        freq_code="A",
                        cl_code="HS",
                        reporter_code=reporter_code,
                        partner_code=partner_code,
                        cmd_code=hs_code,
                        flow_code=fc,
                        period=period,
                    )
                    df = response_to_dataframe(raw)
                    if not df.empty:
                        df = extract_trade_values(df)
                        all_frames.append(df)
                except Exception as e:
                    print(f"   [Skipped] {e}")

                time.sleep(delay_seconds)  # Rate-limit courtesy pause

    if all_frames:
        combined = pd.concat(all_frames, ignore_index=True)
        print(f"\n[OK] Total records fetched: {len(combined)}")
        return combined
    else:
        return pd.DataFrame()


# ─────────────────────────────────────────────
#  BATCH FETCHER (multiple countries / years)
# ─────────────────────────────────────────────

def fetch_batch(
    reporter_codes: List[str],
    periods: List[str],
    cmd_code: str = "TOTAL",
    delay_seconds: float = 1.0,
    **kwargs
) -> pd.DataFrame:
    """
    Loop over multiple reporter codes and periods,
    combining all results into one DataFrame.
    """
    all_frames = []

    for reporter in reporter_codes:
        for period in periods:
            print(f"\n-- Reporter: {reporter} | Period: {period}")
            try:
                raw = fetch_trade_data(
                    reporter_code=reporter,
                    period=period,
                    cmd_code=cmd_code,
                    **kwargs
                )
                df = response_to_dataframe(raw)
                if not df.empty:
                    df = extract_trade_values(df)
                    all_frames.append(df)
            except Exception as e:
                print(f"   [Skipped] {e}")

            time.sleep(delay_seconds)

    if all_frames:
        combined = pd.concat(all_frames, ignore_index=True)
        print(f"\n[OK] Total records fetched: {len(combined)}")
        return combined
    else:
        return pd.DataFrame()
