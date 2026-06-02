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

    FAOSTAT CPC item codes from numeric sources (Excel/CSV without apostrophe
    protection) lose leading zeros (e.g. 01929 -> 1929). We left-pad to
    width 5 so those subclass codes match the canonical form. Use this for
    the legacy concordance CSV where CPC is stored as a number.

    NOTE: this padding is wrong for genuine 4-digit class codes
    (e.g. FAOSTAT's '0111' for Wheat). For sources where the original length
    is meaningful (apostrophe-string protected), use ``normalize_cpc_raw``.
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


def normalize_cpc_raw(code: object) -> Optional[str]:
    """Return CPC string preserving original length (no zero-padding).

    Use for sources that protect leading zeros explicitly (apostrophe-prefixed
    strings in FAOSTAT bulk CSVs, or the rebuilt RASFF concordance). The
    length carries the hierarchy level:

    * 4-digit class       e.g. ``0111`` Wheat
    * 5-digit subclass    e.g. ``01371`` Almonds
    * Dotted sub-subclass e.g. ``01199.90`` Cereals n.e.c.
    * F-prefix aggregate  e.g. ``F1717`` Cereals; primary

    Returns None for unrecognised input. Note the ``.0`` "looks like a float"
    artefact is only stripped when nothing follows it (i.e. ``1929.0`` ->
    ``1929``); dotted CPCs like ``01199.90`` are preserved as-is.
    """
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return None
    s = str(code).strip().lstrip("'")
    if not s:
        return None
    # Pandas-float artefact: "1929.0" -> "1929". Only strip when the trailing
    # ".0" represents an integer value (no other dot in the string).
    if s.endswith(".0") and s.count(".") == 1:
        s = s[:-2]
    # F-prefix aggregates (e.g. F1717)
    if s.startswith("F") and s[1:].replace(".", "").isdigit():
        return s
    # Plain digit codes (4 or 5 char) or dotted FAOSTAT codes (e.g. 01199.90)
    if s.replace(".", "").isdigit():
        return s
    return None


def _get_csv_path() -> Path:
    """Resolve path to the commodities CSV relative to this package."""
    return Path(__file__).resolve().parent.parent.parent / "unique_commodities_hs_cpc.csv"


def _get_rasff_curated_path() -> Path:
    """Path to the hand-curated RASFF HS -> FAOSTAT CPC concordance.

    This file maps every RASFF-flagged HS code to the FAOSTAT QCL Item / CPC
    that actually represents its primary commodity. It is authoritative for
    FAOSTAT production lookups (the legacy ``unique_commodities_hs_cpc.csv``
    uses a different CPC vocabulary and fails to join with FAOSTAT data).
    """
    return Path(__file__).resolve().parent.parent.parent / "rasff_hs_to_faostat_cpc.csv"


@lru_cache(maxsize=1)
def load_rasff_curated_concordance() -> pd.DataFrame:
    """Load the curated RASFF HS -> FAOSTAT CPC map.

    Returns a DataFrame with columns ``hs`` (zero-padded), ``cpc`` (preserves
    FAOSTAT's hierarchical length — 4 digits for class codes, 5 for subclass,
    F-prefix for aggregates), and ``item`` (human-readable). Rows whose codes
    don't normalise are dropped.

    Returns an empty DataFrame when the file is missing so callers can fall
    back to the legacy concordance.
    """
    path = _get_rasff_curated_path()
    if not path.exists():
        return pd.DataFrame(columns=["hs", "cpc", "item"])
    df = pd.read_csv(path, dtype=str)
    df["hs"] = df["hs_code"].apply(normalize_hs)
    df["cpc"] = df["faostat_cpc"].apply(normalize_cpc_raw)
    df = df.dropna(subset=["hs", "cpc"])
    df["item"] = df.get("faostat_item", "")
    return df[["hs", "cpc", "item"]].drop_duplicates().reset_index(drop=True)


@lru_cache(maxsize=1)
def cpc_to_hs_for_production() -> dict[str, list[str]]:
    """Inverse CPC -> list[HS] for production accumulators.

    Two-layer combine:

    1. **Curated override** (``rasff_hs_to_faostat_cpc.csv``) — special cases
       like FishStat CPCs for seafood (``04330`` mussels) that need their own
       coding path.
    2. **Canonical concordance** (``unique_commodities_hs_cpc.csv``,
       maintained by the rebuild script) — every loaded RASFF HS with the
       FAOSTAT QCL CPC for its primary commodity.

    Returns ``{}`` when neither source resolves; callers should then skip
    production lookups for those HS codes.
    """
    out: dict[str, set[str]] = {}

    # Layer 1: curated overrides.
    df = load_rasff_curated_concordance()
    for _, row in df.iterrows():
        out.setdefault(row["cpc"], set()).add(row["hs"])

    # Layer 2: canonical concordance.
    try:
        canonical = load_hs_cpc_concordance()
    except FileNotFoundError:
        canonical = pd.DataFrame()
    if not canonical.empty and "cpc" in canonical.columns:
        for _, row in canonical.iterrows():
            cpc = (row.get("cpc") or "").strip()
            hs = (row.get("hs") or "").strip()
            if cpc and hs:
                out.setdefault(cpc, set()).add(hs)
    return {k: sorted(v) for k, v in out.items()}


def _get_rasff_fbs_path() -> Path:
    """Path to the curated RASFF HS -> FAOSTAT FBS item concordance.

    Maps each RASFF HS code to the FBS aggregate item that represents its
    primary commodity for the food-balance side (domestic supply, food supply,
    stock variation). FBS items use codes like 'S2511 Wheat and products' that
    don't map 1:1 with HS, hence the curation.
    """
    return Path(__file__).resolve().parent.parent.parent / "rasff_hs_to_faostat_fbs.csv"


@lru_cache(maxsize=1)
def load_rasff_fbs_concordance() -> pd.DataFrame:
    """Load curated RASFF HS -> FAOSTAT FBS item map.

    Returns columns ``hs`` (zero-padded), ``fbs_item_code`` (e.g. 'S2511'),
    ``fbs_item`` (human-readable label). Empty DataFrame when the file is
    missing — callers fall back to the keyword-bridge mapping.
    """
    path = _get_rasff_fbs_path()
    if not path.exists():
        return pd.DataFrame(columns=["hs", "fbs_item_code", "fbs_item"])
    df = pd.read_csv(path, dtype=str)
    df["hs"] = df["hs_code"].apply(normalize_hs)
    df["fbs_item_code"] = df["fbs_item_code"].astype(str).str.strip().str.lstrip("'")
    df["fbs_item"] = df.get("fbs_item", "").astype(str).str.strip()
    df = df.dropna(subset=["hs", "fbs_item_code"])
    return df[["hs", "fbs_item_code", "fbs_item"]].drop_duplicates().reset_index(drop=True)


@lru_cache(maxsize=1)
def fbs_item_to_hs() -> dict[str, list[str]]:
    """Inverse map: FBS item code -> list[RASFF HS].

    Combines two sources:

    1. The curated ``rasff_hs_to_faostat_fbs.csv`` (highest priority, used for
       special overrides).
    2. The rebuilt canonical concordance ``unique_commodities_hs_cpc.csv``
       which carries ``fbs_item_code`` per row.

    Returns empty dict when no FBS mapping is loaded, in which case callers
    fall back to the legacy keyword-bridge approach.
    """
    out: dict[str, set[str]] = {}

    # Layer 1: explicit curated overrides.
    df = load_rasff_fbs_concordance()
    for _, row in df.iterrows():
        out.setdefault(row["fbs_item_code"], set()).add(row["hs"])

    # Layer 2: canonical concordance (HS -> FBS code is already in the file).
    try:
        canonical = load_hs_cpc_concordance()
    except FileNotFoundError:
        canonical = pd.DataFrame()
    if not canonical.empty and "fbs_item_code" in canonical.columns:
        for _, row in canonical.iterrows():
            code = (row.get("fbs_item_code") or "").strip()
            hs = (row.get("hs") or "").strip()
            if code and hs:
                out.setdefault(code, set()).add(hs)
    return {k: sorted(v) for k, v in out.items()}


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
    """Load the unified RASFF HS -> FAOSTAT concordance.

    The file is rebuilt against FAOSTAT's actual CPC vocabulary by
    ``script/rebuild_hs_concordance.py`` and carries both the production-side
    CPC and the FBS item code per HS. Returns columns:

      * ``commodity`` — human-readable label from the RASFF source
      * ``hs``        — normalised HS code (zero-padded)
      * ``cpc``       — FAOSTAT CPC at its native length (may be ``""`` when
                        the HS is out of QCL scope, e.g. fish / non-food)
      * ``fbs_item_code`` — FBS aggregate code (e.g. ``S2767``) or ``""``
      * ``faostat_item``   — friendly item label for debugging
      * ``confidence``     — ``override`` | ``heading`` | ``chapter`` | ``unmapped``

    Empty CPC / FBS strings are kept in the frame so callers can filter on
    them explicitly. Use ``normalize_cpc_raw`` (length-preserving) — the
    rebuilt file holds CPCs at their natural FAOSTAT length (4-digit class,
    5-digit subclass, F-prefix aggregate).
    """
    path = _get_csv_path()
    if not path.exists():
        raise FileNotFoundError(f"Commodities CSV not found: {path}")
    df = pd.read_csv(path, dtype=str).fillna("")
    df["hs"] = df["hs_code_comtrade"].apply(normalize_hs)
    df["cpc"] = df["faostat_cpc"].apply(
        lambda v: normalize_cpc_raw(v) if v else ""
    ).fillna("")
    df["fbs_item_code"] = df.get("fbs_item_code", "").astype(str).str.strip()
    df["faostat_item"] = df.get("faostat_item", "").astype(str).str.strip()
    df["confidence"] = df.get("mapping_confidence", "").astype(str).str.strip()
    df = df.dropna(subset=["hs"])
    return df[["commodity", "hs", "cpc", "fbs_item_code", "faostat_item", "confidence"]].drop_duplicates().reset_index(drop=True)


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
