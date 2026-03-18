"""
HS Codes Loader

Loads HS codes from the unique_commodities_hs_cpc.csv file.
"""

import os
import pandas as pd
from pathlib import Path
from typing import List, Dict, Optional


def get_commodities_csv_path() -> Path:
    """Get the path to the unique commodities CSV file."""
    # Get the backend directory (parent of script folder)
    script_dir = Path(__file__).parent
    backend_dir = script_dir.parent
    return backend_dir / "unique_commodities_hs_cpc.csv"


def load_commodities_data() -> pd.DataFrame:
    """
    Load the commodities data from CSV.

    Returns:
        DataFrame with columns: commodity, hs_code_comtrade, faostat_cpc
    """
    csv_path = get_commodities_csv_path()

    if not csv_path.exists():
        raise FileNotFoundError(f"Commodities CSV not found at: {csv_path}")

    df = pd.read_csv(csv_path)
    return df


def get_unique_hs_codes() -> List[str]:
    """
    Get list of unique HS codes from the commodities CSV.

    Returns:
        List of unique HS code strings
    """
    df = load_commodities_data()

    # Get unique HS codes, drop NaN values, convert to string
    hs_codes = df["hs_code_comtrade"].dropna().unique()

    # Convert to strings and ensure proper formatting
    # HS codes should be strings to preserve leading zeros
    hs_codes_list = [str(int(code)) if pd.notna(code) else None for code in hs_codes]
    hs_codes_list = [code for code in hs_codes_list if code is not None]

    return hs_codes_list


def get_hs_codes_with_names() -> Dict[str, List[str]]:
    """
    Get dictionary mapping HS codes to their commodity names.

    Returns:
        Dict with HS code as key and list of commodity names as value
    """
    df = load_commodities_data()

    hs_to_names = {}

    for _, row in df.iterrows():
        hs_code = row["hs_code_comtrade"]
        commodity = row["commodity"]

        if pd.notna(hs_code):
            hs_code_str = str(int(hs_code))
            if hs_code_str not in hs_to_names:
                hs_to_names[hs_code_str] = []
            hs_to_names[hs_code_str].append(commodity)

    return hs_to_names


def get_commodities_by_hs_code(hs_code: str) -> List[str]:
    """
    Get list of commodity names for a specific HS code.

    Args:
        hs_code: The HS code to look up

    Returns:
        List of commodity names
    """
    hs_to_names = get_hs_codes_with_names()
    return hs_to_names.get(hs_code, [])


def filter_hs_codes_by_chapter(chapter: str) -> List[str]:
    """
    Filter HS codes by chapter (first 2 digits).

    Args:
        chapter: Two-digit chapter code (e.g., "03" for fish, "10" for cereals)

    Returns:
        List of HS codes starting with that chapter
    """
    all_codes = get_unique_hs_codes()
    return [code for code in all_codes if code.startswith(chapter)]


def get_hs_code_summary() -> pd.DataFrame:
    """
    Get summary statistics of HS codes in the dataset.

    Returns:
        DataFrame with HS code, count of commodities, and sample names
    """
    hs_to_names = get_hs_codes_with_names()

    summary_data = []
    for hs_code, names in hs_to_names.items():
        summary_data.append({
            "hs_code": hs_code,
            "commodity_count": len(names),
            "sample_commodities": ", ".join(names[:3]) + ("..." if len(names) > 3 else "")
        })

    return pd.DataFrame(summary_data).sort_values("commodity_count", ascending=False)


if __name__ == "__main__":
    # Test the loader
    print("Loading commodities data...")
    df = load_commodities_data()
    print(f"Total commodities: {len(df)}")

    print("\nUnique HS codes:")
    hs_codes = get_unique_hs_codes()
    print(f"Count: {len(hs_codes)}")
    print(f"Sample: {hs_codes[:10]}")

    print("\nHS Code Summary:")
    summary = get_hs_code_summary()
    print(summary.head(10))
