"""
UN Comtrade API client.

Refactored from backend/script/comtrade_fetcher.py.
Fetches bilateral trade data for commodity-country pairs.
"""

import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from defensefood.ingestion.comtrade_keys import (
    QuotaExhausted,
    get_key_pool,
    is_quota_http_error,
)

BASE_URL = "https://comtradeapi.un.org/data/v1/get"

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

    pool = get_key_pool()
    while True:
        try:
            response = requests.get(url, headers=pool.headers(), params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            body = (getattr(e.response, "text", "") or "").strip()
            if is_quota_http_error(status, body) and pool.rotate():
                continue
            if is_quota_http_error(status, body):
                raise QuotaExhausted(body[:200] or "HTTP 403: all keys out of quota") from e
            raise


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


def _output_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "script" / "output"


def _newest(paths: list[Path]) -> Optional[Path]:
    return max(paths, key=lambda p: p.stat().st_mtime) if paths else None


def load_merged_trade_data(path: Optional[Path] = None) -> pd.DataFrame:
    """Load the trade CSV used for dependency / trade-flow metrics.

    Preference order (newest within each tier):
      1. explicit ``path`` if given
      2. ``merged_trade_data.csv`` (canonical, from ``script/merge_output_csv.py``)
      3. ``comtrade_all_partners_*.csv`` (full partner breakdown -> correct OCS/HHI)
      4. ``rasff_trade_all_pairs_*.csv`` (curated RASFF pairs -- biased OCS/HHI)

    The all-partners file is preferred over the curated pairs because it gives
    each reporter's complete import-partner set, which the Section 2 OCS/HHI
    denominators require. Note: do NOT merge both tiers into one file (e.g. via
    merge_output_csv.py) or partner rows will double-count.
    """
    if path is not None:
        if not path.exists():
            raise FileNotFoundError(f"Merged trade CSV not found: {path}")
        return pd.read_csv(path)

    out = _output_dir()
    merged = out / "merged_trade_data.csv"
    if merged.exists():
        return pd.read_csv(merged)

    all_partners = _newest(list(out.glob("comtrade_all_partners_*.csv")))
    if all_partners is not None:
        return pd.read_csv(all_partners)

    all_pairs = _newest(list(out.glob("rasff_trade_all_pairs_*.csv")))
    if all_pairs is not None:
        return pd.read_csv(all_pairs)

    raise FileNotFoundError(
        f"No trade CSV in {out} (looked for merged_trade_data.csv, "
        "comtrade_all_partners_*.csv, rasff_trade_all_pairs_*.csv)"
    )
