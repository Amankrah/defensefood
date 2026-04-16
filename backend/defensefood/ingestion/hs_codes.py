"""
HS code and commodity mapping loader.

Refactored from backend/script/hs_codes_loader.py.
Loads the unique_commodities_hs_cpc.csv mapping file.
"""

from pathlib import Path

import pandas as pd


def _get_csv_path() -> Path:
    """Resolve path to the commodities CSV relative to this package."""
    return Path(__file__).resolve().parent.parent.parent / "unique_commodities_hs_cpc.csv"


def load_commodities_data() -> pd.DataFrame:
    """Load the commodities CSV (commodity, hs_code_comtrade, faostat_cpc)."""
    path = _get_csv_path()
    if not path.exists():
        raise FileNotFoundError(f"Commodities CSV not found: {path}")
    df = pd.read_csv(path)
    df["hs_code_comtrade"] = df["hs_code_comtrade"].apply(
        lambda x: str(int(x)) if pd.notna(x) else None
    )
    return df


def get_unique_hs_codes() -> list[str]:
    """Return sorted list of unique HS codes."""
    df = load_commodities_data()
    return sorted(df["hs_code_comtrade"].dropna().unique().tolist())


def get_hs_codes_with_names() -> dict[str, list[str]]:
    """Return mapping: HS code -> list of commodity names."""
    df = load_commodities_data()
    result: dict[str, list[str]] = {}
    for _, row in df.iterrows():
        code = row["hs_code_comtrade"]
        name = row["commodity"]
        if code and pd.notna(name):
            result.setdefault(code, []).append(str(name))
    return result


def filter_hs_codes_by_chapter(chapter: str) -> list[str]:
    """Filter HS codes by 2-digit chapter prefix (e.g. '03' for seafood)."""
    codes = get_unique_hs_codes()
    return [c for c in codes if c.startswith(chapter)]
