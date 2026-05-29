"""
HS code and commodity mapping loader.

Refactored from backend/script/hs_codes_loader.py.
Loads the unique_commodities_hs_cpc.csv mapping file.

Also provides canonical code normalisation shared across RASFF, Comtrade trade,
and FAOSTAT joins. Comtrade/RASFF/concordance all store codes as integers, which
strips leading zeros (e.g. HS 030617 -> 30617, CPC 01929 -> 1929). The helpers
here restore a canonical zero-padded string form so the three sources line up.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd


def normalize_hs(code: object) -> Optional[str]:
    """Return canonical zero-padded HS string, or None if unusable.

    HS codes are 2/4/6 digits. Sources that read codes as integers drop a
    leading zero, so a 6-digit fish code 030617 arrives as "30617" (5 chars).
    We left-pad odd-length codes by one zero so 5->6, 3->4, 1->2, recovering
    the dropped leading zero. Codes are truncated to at most 6 digits.
    """
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return None
    s = str(code).strip()
    if s.endswith(".0"):
        s = s[:-2]
    s = s.lstrip("'")  # FAOSTAT/Excel sometimes prefix a literal apostrophe
    if not s or not s.isdigit():
        return None
    if len(s) % 2 == 1:
        s = "0" + s
    return s[:6]


def hs_prefix(code: object, digits: int) -> Optional[str]:
    """First `digits` digits of the normalised HS code (for rollup matching)."""
    norm = normalize_hs(code)
    if norm is None:
        return None
    return norm[:digits]


def normalize_cpc(code: object) -> Optional[str]:
    """Return canonical 5-digit zero-padded FAOSTAT CPC string, or None.

    FAOSTAT CPC item codes are 5 digits (e.g. 01929). Read as a number they
    lose the leading zero (1929), so we left-pad to width 5.
    """
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return None
    s = str(code).strip()
    if s.endswith(".0"):
        s = s[:-2]
    s = s.lstrip("'")
    if not s or not s.isdigit():
        return None
    return s.zfill(5)


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


@lru_cache(maxsize=1)
def load_hs_cpc_concordance() -> pd.DataFrame:
    """Load the HS<->CPC concordance with canonical, normalised codes.

    Returns a DataFrame with columns: commodity, hs (zero-padded), cpc
    (5-digit). Rows whose codes don't normalise are dropped.
    """
    path = _get_csv_path()
    if not path.exists():
        raise FileNotFoundError(f"Commodities CSV not found: {path}")
    df = pd.read_csv(path)
    df["hs"] = df["hs_code_comtrade"].apply(normalize_hs)
    df["cpc"] = df["faostat_cpc"].apply(normalize_cpc)
    df = df.dropna(subset=["hs", "cpc"])
    return df[["commodity", "hs", "cpc"]].drop_duplicates().reset_index(drop=True)


@lru_cache(maxsize=1)
def hs_to_cpc_map() -> dict[str, list[str]]:
    """Map a normalised HS code to the list of FAOSTAT CPC item codes under it.

    One HS heading can cover several CPC items (e.g. distinct commodities that
    share a 6-digit HS). Callers that need production for an HS should sum over
    all mapped CPC items. A 4-digit-prefix fallback key is also added so that
    HS headings (e.g. 1006) still resolve when only 6-digit children are mapped.
    """
    conc = load_hs_cpc_concordance()
    out: dict[str, set[str]] = {}
    for _, row in conc.iterrows():
        out.setdefault(row["hs"], set()).add(row["cpc"])
        # 4-digit rollup key so headings match their 6-digit children
        out.setdefault(row["hs"][:4], set()).add(row["cpc"])
    return {k: sorted(v) for k, v in out.items()}


def cpc_for_hs(hs_code: object) -> list[str]:
    """Resolve CPC item codes for an HS code, trying exact then 4-digit rollup."""
    norm = normalize_hs(hs_code)
    if norm is None:
        return []
    mapping = hs_to_cpc_map()
    if norm in mapping:
        return mapping[norm]
    return mapping.get(norm[:4], [])
