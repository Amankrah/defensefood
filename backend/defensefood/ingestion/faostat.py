"""
FAOSTAT data ingestion -- production (P), domestic supply (D), population.

Feeds the dependency (Section 2) and consumption (Section 3) models with the
balance-sheet quantities the framework's worked examples assume.

Data source: FAOSTAT bulk-download CSVs (the "All Data Normalized" long format)
plus FAO FishStat Global Production for seafood capture/aquaculture P.

Three production/supply domains:

  * QCL  -- "Crops and livestock products"  -> Element "Production"
  * FBS  -- "Food Balance Sheets"           -> Elements "Domestic supply
            quantity", "Food supply quantity (kg/capita/yr)",
            "Total Population - Both sexes", "Stock variation"
  * FishStat -- ``Global_production_quantity.csv`` (capture + aquaculture,
            tonnes live weight) keyed by ASFIS species -> CPC via
            ``CL_FI_SPECIES_GROUPS.csv``

Both are keyed by `Item Code (CPC)` and `Area Code (M49)`. We join CPC -> HS via
``unique_commodities_hs_cpc.csv`` so production can be looked up by the same HS
code the trade/RASFF corridors use.

Files are read from ``DEFENSEFOOD_FAOSTAT_DIR`` (default ``backend/data/faostat``).
When no files are present the store loads empty and callers fall back to the
trade-only DS' proxy (DS' = M - X), tagged with provenance so the UI can say so.
"""

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

from defensefood.ingestion.hs_codes import cpc_for_hs, normalize_cpc, normalize_cpc_raw

logger = logging.getLogger(__name__)

# FAOSTAT element labels we care about (lower-cased, matched as substrings so
# minor wording/case differences across releases still resolve).
_PRODUCTION_ELEMENTS = ("production",)
_DOMESTIC_SUPPLY_ELEMENTS = ("domestic supply quantity",)
_POPULATION_ELEMENTS = ("total population - both sexes", "total population")
_STOCK_VARIATION_ELEMENTS = ("stock variation",)

# Column-name candidates across FAOSTAT releases.
_COL_CANDIDATES = {
    "area_m49": ("Area Code (M49)", "Area Code M49", "Area Code"),
    "item_cpc": ("Item Code (CPC)", "Item Code CPC", "Item Code"),
    "item_fbs": ("Item Code (FBS)", "Item Code FBS"),
    "element": ("Element",),
    "year": ("Year", "Year Code"),
    "unit": ("Unit",),
    "value": ("Value",),
}

_TONNE_TO_KG = 1_000.0
_KILOTONNE_TO_KG = 1_000_000.0  # FAOSTAT "1000 t"
_THOUSAND = 1_000.0  # FAOSTAT "1000 persons" / "1000 No"


def _faostat_dir(data_dir: Optional[Path] = None) -> Path:
    if data_dir is not None:
        return Path(data_dir)
    env = os.environ.get("DEFENSEFOOD_FAOSTAT_DIR", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent / "data" / "faostat"


def _resolve_col(df: pd.DataFrame, key: str) -> Optional[str]:
    for cand in _COL_CANDIDATES[key]:
        if cand in df.columns:
            return cand
    return None


def _find_files(
    directory: Path,
    *keywords: str,
    exclude: tuple[str, ...] = (),
) -> list[Path]:
    """CSV files under `directory` whose name contains any keyword (case-insensitive).

    FAOSTAT bulk zips unpack into subfolders (e.g.
    ``Production_Crops_Livestock_E_All_Data_(Normalized)/...csv``), so we search
    recursively. Metadata sidecars (ItemCodes, AreaCodes, Elements, Flags) are
    skipped; only the main long-format data file is loaded.
    """
    if not directory.is_dir():
        return []
    skip_fragments = ("itemcodes", "areacodes", "elements", "flags", "cl_fi_", "fsj_")
    out: list[Path] = []
    for p in sorted(directory.rglob("*.csv")):
        name = p.name.lower()
        if any(s in name for s in skip_fragments):
            continue
        if any(ex.lower() in name for ex in exclude):
            continue
        if any(k.lower() in name for k in keywords):
            out.append(p)
    return out


def _to_m49(value: object) -> Optional[int]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip().lstrip("'")
    if s.endswith(".0"):
        s = s[:-2]
    if not s.isdigit():
        return None
    return int(s)


def _is_fbs_frame(df: pd.DataFrame) -> bool:
    """True when this bulk file is Food Balance Sheets (FBS item codes, not CPC)."""
    return "Item Code (FBS)" in df.columns or "foodbalance" in str(df.columns).lower()


def _normalise_long(df: pd.DataFrame, *, fbs: bool = False) -> Optional[pd.DataFrame]:
    """Reduce a raw FAOSTAT bulk frame to long columns for accumulation."""
    cols = {k: _resolve_col(df, k) for k in _COL_CANDIDATES}
    required = ("area_m49", "element", "year", "value")
    if any(cols[k] is None for k in required):
        logger.warning("FAOSTAT file missing required columns; skipping (have %s)", list(df.columns)[:12])
        return None

    out = pd.DataFrame({
        "m49": df[cols["area_m49"]].map(_to_m49),
        "element": df[cols["element"]].astype(str).str.strip().str.lower(),
        "year": pd.to_numeric(df[cols["year"]], errors="coerce"),
        "value": pd.to_numeric(df[cols["value"]], errors="coerce"),
    })
    out["unit"] = df[cols["unit"]].astype(str).str.strip().str.lower() if cols["unit"] else ""
    if fbs:
        # FBS rows use aggregate SUA item codes (e.g. S2807 Rice and products),
        # not CPC. Keep the label for the legacy keyword-bridge fallback AND
        # the stable item code for the curated FBS->HS map.
        out["item_label"] = (
            df["Item"].astype(str).str.strip().str.lower()
            if "Item" in df.columns
            else ""
        )
        fbs_col = cols.get("item_fbs")
        out["fbs_item_code"] = (
            df[fbs_col].astype(str).str.strip().str.lstrip("'") if fbs_col else ""
        )
        out["cpc"] = None
    else:
        out["item_label"] = ""
        # Use the length-preserving normaliser. FAOSTAT bulk CSVs apostrophe-protect
        # the CPC column, so the natural length carries the hierarchy level
        # (4-digit = class, 5-digit = subclass, F-prefix = aggregate). zfilling
        # them would conflate '0111' (Wheat) with '00111' (a different code).
        out["cpc"] = df[cols["item_cpc"]].map(normalize_cpc_raw) if cols["item_cpc"] else None
    out = out.dropna(subset=["m49", "year", "value"])
    out["m49"] = out["m49"].astype(int)
    out["year"] = out["year"].astype(int)
    return out


def _value_to_kg(value: float, unit: str) -> float:
    """Convert a FAOSTAT quantity to kilograms based on its unit string."""
    u = (unit or "").strip().lower()
    if u in ("1000 t", "1000 tonnes", "kt"):
        return value * _KILOTONNE_TO_KG
    if u in ("t", "tonnes", "tonne"):
        return value * _TONNE_TO_KG
    if u == "kg":
        return value
    # Unknown unit: assume tonnes (FAOSTAT's most common production unit).
    return value * _TONNE_TO_KG


def _match_element(element: str, wanted: tuple[str, ...]) -> bool:
    return any(w in element for w in wanted)


@dataclass
class FaostatStore:
    """In-memory FAOSTAT lookups, indexed by HS where commodity-specific.

    `production_kg` / `domestic_supply_kg` are keyed (hs, m49, year) and already
    summed over every CPC item mapped to that HS. `population` is keyed
    (m49, year). `available` is False when no usable files were found.

    Nearest-year fallback: FAOSTAT FBS and QCL data typically lag trade by 1-3
    years (especially preliminary releases). When an exact-year lookup misses,
    the getters walk back up to ``fallback_years`` years before giving up.
    This means a 2023 trade corridor can still pick up 2022 or 2021 production
    if 2023 is not yet released for that (hs, m49) pair. The fallback is one-
    sided (older only) — we never reach forward to a future year.
    """
    production: dict[tuple[str, int, int], float] = field(default_factory=dict)
    domestic_supply: dict[tuple[str, int, int], float] = field(default_factory=dict)
    # Stock variation (kg) from FBS. Positive = stock draw-down (supply boost);
    # negative = stock build-up. Feeds DS' = P + M - X + ΔS (blueprint Eq. 1).
    stock_variation: dict[tuple[str, int, int], float] = field(default_factory=dict)
    population_by_country: dict[tuple[int, int], float] = field(default_factory=dict)
    available: bool = False
    fallback_years: int = 3

    def _lookup_with_fallback(
        self,
        store: dict,
        key_prefix: tuple,
        year: int,
    ) -> tuple[Optional[float], Optional[int]]:
        """Walk year, year-1, ..., year-fallback_years returning the first hit.

        Returns ``(value, year_used)`` or ``(None, None)`` when no year resolves.
        """
        for y in range(year, year - self.fallback_years - 1, -1):
            v = store.get(key_prefix + (y,))
            if v is not None:
                return v, y
        return None, None

    def production_kg(self, hs: str, m49: int, year: int) -> Optional[float]:
        v, _ = self._lookup_with_fallback(self.production, (hs, m49), year)
        return v

    def production_with_year(
        self, hs: str, m49: int, year: int
    ) -> tuple[Optional[float], Optional[int]]:
        """Like ``production_kg`` but also returns which year was used."""
        return self._lookup_with_fallback(self.production, (hs, m49), year)

    def domestic_supply_kg(self, hs: str, m49: int, year: int) -> Optional[float]:
        v, _ = self._lookup_with_fallback(self.domestic_supply, (hs, m49), year)
        return v

    def domestic_supply_with_year(
        self, hs: str, m49: int, year: int
    ) -> tuple[Optional[float], Optional[int]]:
        """Like ``domestic_supply_kg`` but also returns which year was used."""
        return self._lookup_with_fallback(self.domestic_supply, (hs, m49), year)

    def stock_variation_kg(self, hs: str, m49: int, year: int) -> Optional[float]:
        """ΔS for the year. Positive = drawdown adding to supply."""
        v, _ = self._lookup_with_fallback(self.stock_variation, (hs, m49), year)
        return v

    def population(self, m49: int, year: int) -> Optional[float]:
        v, _ = self._lookup_with_fallback(self.population_by_country, (m49,), year)
        return v


def _hs_codes_for_fbs_item(item_label: str, conc: pd.DataFrame) -> list[str]:
    """Map an FBS aggregate item label to HS codes via concordance keyword match."""
    label = (item_label or "").strip().lower()
    if not label:
        return []

    # HS chapter hints for common FBS aggregates (fallback when name match is weak).
    prefix_hints: list[tuple[str, str]] = [
        ("rice", "1006"),
        ("wheat", "1001"),
        ("barley", "1003"),
        ("maize", "1005"),
        ("mussel", "0307"),
        ("fish", "0302"),
        ("seafood", "0307"),
        ("honey", "0409"),
        ("olive", "1509"),
        ("flax", "1204"),
        ("linseed", "1204"),
        ("feed", "2309"),
    ]
    for needle, prefix in prefix_hints:
        if needle in label:
            hits = sorted({hs for hs in conc["hs"] if hs.startswith(prefix)})
            if hits:
                return hits

    stop = {"and", "the", "other", "products", "excluding", "beer", "n.e.c.", "nec"}
    tokens = [
        t for t in label.replace(",", " ").replace("-", " ").split()
        if len(t) > 2 and t not in stop
    ]
    if not tokens:
        return []

    matched: set[str] = set()
    for _, row in conc.iterrows():
        comm = str(row["commodity"]).lower()
        if any(tok in comm for tok in tokens):
            matched.add(row["hs"])
    return sorted(matched)


def _accumulate_by_hs(
    long_df: pd.DataFrame,
    wanted_elements: tuple[str, ...],
    target: dict[tuple[str, int, int], float],
) -> None:
    """Sum CPC-keyed values into an HS-keyed dict via the concordance.

    Two layers, both speaking FAOSTAT's actual CPC vocabulary:

    1. **Curated overrides** (``rasff_hs_to_faostat_cpc.csv``) — for special
       cases that need different codes than the canonical concordance, e.g.
       FishStat CPCs for seafood lanes (``04330`` mussels, ``04240`` shrimps).
    2. **Rebuilt canonical concordance** (``unique_commodities_hs_cpc.csv``,
       maintained by ``script/rebuild_hs_concordance.py``) — covers every
       loaded RASFF HS with FAOSTAT QCL CPC. Rows without a CPC (non-food
       chapters, FBS-only items) are skipped.
    """
    from defensefood.ingestion.hs_codes import (
        cpc_to_hs_for_production,
        load_hs_cpc_concordance,
    )

    rows = long_df[long_df["element"].map(lambda e: _match_element(e, wanted_elements))]

    # Primary: curated FAOSTAT-CPC -> RASFF-HS map (overrides).
    cpc_to_hs_cache: dict[str, list[str]] = dict(cpc_to_hs_for_production())
    curated_keys = set(cpc_to_hs_cache.keys())

    # Secondary: canonical concordance. Skip rows with no CPC (out-of-scope HS
    # codes) and let curated win on collisions.
    legacy = load_hs_cpc_concordance()
    legacy = legacy[legacy["cpc"].astype(bool)]
    for cpc, grp in legacy.groupby("cpc"):
        if cpc in curated_keys:
            continue
        cpc_to_hs_cache[cpc] = sorted(set(grp["hs"]))

    matched = 0
    for _, r in rows.iterrows():
        cpc = r["cpc"]
        if cpc is None or cpc not in cpc_to_hs_cache:
            continue
        kg = _value_to_kg(float(r["value"]), r["unit"])
        m49, year = int(r["m49"]), int(r["year"])
        for hs in cpc_to_hs_cache[cpc]:
            key = (hs, m49, year)
            target[key] = target.get(key, 0.0) + kg
        matched += 1
    if matched:
        logger.info(
            "FAOSTAT accumulator matched %d production rows across %d CPC keys "
            "(%d curated, %d legacy fallback)",
            matched, len(cpc_to_hs_cache),
            len(curated_keys), len(cpc_to_hs_cache) - len(curated_keys),
        )


def _accumulate_fbs_by_hs(
    long_df: pd.DataFrame,
    wanted_elements: tuple[str, ...],
    target: dict[tuple[str, int, int], float],
    *,
    sum_mode: str = "add",
) -> None:
    """Map an FBS element (supply, stock variation, ...) onto HS-keyed dicts.

    Lookup order:
      1. **Curated FBS item code -> HS map** (``rasff_hs_to_faostat_fbs.csv``).
         Authoritative when present; uses stable FBS item codes like ``S2767``.
      2. **Legacy keyword bridge** (``_hs_codes_for_fbs_item``). Used only for
         FBS items the curated file doesn't cover, so existing behaviour for
         non-RASFF lanes still works.

    ``sum_mode='add'`` accumulates kg additively (the right thing for both
    supply and signed stock variation — FBS stock-variation values are already
    signed: positive = drawdown into supply, negative = build-up out of supply).
    """
    from defensefood.ingestion.hs_codes import fbs_item_to_hs, load_hs_cpc_concordance

    rows = long_df[long_df["element"].map(lambda e: _match_element(e, wanted_elements))]
    curated = fbs_item_to_hs()
    conc = load_hs_cpc_concordance()
    label_cache: dict[str, list[str]] = {}

    matched = 0
    for _, r in rows.iterrows():
        code = str(r.get("fbs_item_code") or "")
        hs_codes = curated.get(code)
        if not hs_codes:
            label = str(r.get("item_label") or "")
            if label not in label_cache:
                label_cache[label] = _hs_codes_for_fbs_item(label, conc)
            hs_codes = label_cache[label]
        if not hs_codes:
            continue
        kg = _value_to_kg(float(r["value"]), r["unit"])
        m49, year = int(r["m49"]), int(r["year"])
        for hs in hs_codes:
            key = (hs, m49, year)
            target[key] = target.get(key, 0.0) + kg
        matched += 1
    if matched:
        logger.info(
            "FAOSTAT FBS accumulator (%s): matched %d rows; curated keys=%d, "
            "keyword-bridge labels=%d",
            ",".join(wanted_elements), matched, len(curated), len(label_cache),
        )


# Backwards-compatible thin wrapper for callers that imported the old name.
def _accumulate_fbs_domestic_by_hs(
    long_df: pd.DataFrame,
    target: dict[tuple[str, int, int], float],
) -> None:
    _accumulate_fbs_by_hs(long_df, _DOMESTIC_SUPPLY_ELEMENTS, target)


# ---------------------------------------------------------------------------
#  FishStat Global Production (seafood P)
# ---------------------------------------------------------------------------

# ISSCAAP commodity groups -> FAOSTAT CPC subclass (Section 4 aquatic products).
_ISSCAAP_TO_CPC: dict[str, str] = {
    "Shrimps, prawns": "04240",
    "Mussels": "04330",
    "Oysters": "04310",
    "Clams, cockles, arkshells": "04360",
    "Scallops, pectens": "04390",
    "Miscellaneous marine molluscs": "04390",
    "Freshwater molluscs": "04390",
    "Abalones, winkles, conchs": "04390",
    "Crabs, sea-spiders": "04240",
    "King crabs, squat-lobsters": "04240",
    "Lobsters, spiny-rock lobsters": "04240",
    "Freshwater crustaceans": "04240",
    "Miscellaneous marine crustaceans": "04240",
    "Krill, planktonic crustaceans": "04240",
}


def _cpc_for_fish_species(isscaap: str, name_en: str, major_group: str) -> Optional[str]:
    """Map an ASFIS species row to a CPC subclass for RASFF seafood production."""
    group = (isscaap or "").strip()
    name = (name_en or "").lower()
    major = (major_group or "").strip().upper()

    if group == "Squids, cuttlefishes, octopuses":
        if "octopus" in name:
            return "04350"
        return "04340"

    if group in _ISSCAAP_TO_CPC:
        return _ISSCAAP_TO_CPC[group]
    if major == "CRUSTACEA":
        return "04240"
    if major == "MOLLUSCA":
        return "04390"
    return None


@lru_cache(maxsize=4)
def _load_asfis_to_cpc(species_csv: str) -> dict[str, str]:
    """Build ASFIS 3A_Code -> CPC map from ``CL_FI_SPECIES_GROUPS.csv``."""
    path = Path(species_csv)
    if not path.is_file():
        return {}
    df = pd.read_csv(path, usecols=["3A_Code", "ISSCAAP_Group_En", "Name_En", "Major_Group"], low_memory=False)
    out: dict[str, str] = {}
    for _, row in df.iterrows():
        code = str(row["3A_Code"]).strip()
        cpc = _cpc_for_fish_species(
            str(row.get("ISSCAAP_Group_En") or ""),
            str(row.get("Name_En") or ""),
            str(row.get("Major_Group") or ""),
        )
        if cpc:
            out[code] = cpc
    return out


def _find_fishstat_files(directory: Path) -> tuple[Optional[Path], Optional[Path]]:
    """Return (production_quantity_csv, species_groups_csv) when present."""
    prod_files = _find_files(directory, "global_production_quantity")
    if not prod_files:
        return None, None
    prod = prod_files[0]
    species = prod.parent / "CL_FI_SPECIES_GROUPS.csv"
    if not species.is_file():
        hits = sorted(directory.rglob("CL_FI_SPECIES_GROUPS.csv"))
        species = hits[0] if hits else None
    return prod, species if species and Path(species).is_file() else None


def _accumulate_fishstat_production(
    production_path: Path,
    species_path: Optional[Path],
    target: dict[tuple[str, int, int], float],
) -> None:
    """Sum FishStat capture + aquaculture into ``target`` via CPC -> HS join.

    Aggregates ``Global_production_quantity.csv`` to national totals:
    all fishing areas, capture + aquaculture, ``Q_tlw`` (tonnes live weight).
    """
    asfis_map = _load_asfis_to_cpc(str(species_path)) if species_path else {}
    if not asfis_map:
        logger.warning(
            "FishStat production file %s found but no species CPC map (%s); skipping",
            production_path.name,
            species_path,
        )
        return

    df = pd.read_csv(production_path, low_memory=False)
    required = {
        "COUNTRY.UN_CODE", "SPECIES.ALPHA_3_CODE", "MEASURE", "PERIOD", "VALUE",
    }
    if not required.issubset(df.columns):
        logger.warning(
            "FishStat file missing columns; skipping (have %s)", list(df.columns)[:12]
        )
        return

    df = df[df["MEASURE"].astype(str).str.upper() == "Q_TLW"].copy()
    df["m49"] = df["COUNTRY.UN_CODE"].map(_to_m49)
    df["year"] = pd.to_numeric(df["PERIOD"], errors="coerce")
    df["value"] = pd.to_numeric(df["VALUE"], errors="coerce")
    df["cpc"] = df["SPECIES.ALPHA_3_CODE"].astype(str).str.strip().map(asfis_map)
    df = df.dropna(subset=["m49", "year", "value", "cpc"])
    if df.empty:
        logger.warning("FishStat production file %s had no usable Q_tlw rows", production_path.name)
        return

    # National total: sum every fishing area and both capture + aquaculture.
    agg = (
        df.groupby(["m49", "cpc", "year"], as_index=False)["value"]
        .sum()
        .rename(columns={"value": "value"})
    )
    long_df = pd.DataFrame({
        "m49": agg["m49"].astype(int),
        "year": agg["year"].astype(int),
        "value": agg["value"].astype(float),
        "unit": "t",
        "cpc": agg["cpc"].astype(str),
        "element": "production",
        "item_label": "",
    })
    before = len(target)
    _accumulate_by_hs(long_df, _PRODUCTION_ELEMENTS, target)
    added = len(target) - before
    logger.info(
        "FishStat production: %s -> %d CPC-country-year rows, %d new HS production keys",
        production_path.name, len(long_df), added,
    )


def load_faostat_store(data_dir: Optional[Path] = None) -> FaostatStore:
    """Build the FAOSTAT lookup store from bulk CSVs in the data directory.

    Returns an empty (available=False) store when no files are found, so the
    rest of the pipeline keeps working in trade-only mode.
    """
    directory = _faostat_dir(data_dir)
    store = FaostatStore()

    prod_files = _find_files(
        directory, "production", "qcl", "crops_livestock",
        exclude=("global_production",),
    )
    fbs_files = _find_files(directory, "food_balance", "foodbalance", "fbs")
    fish_prod, fish_species = _find_fishstat_files(directory)

    if not prod_files and not fbs_files and fish_prod is None:
        logger.warning(
            "No FAOSTAT CSVs found in %s; dependency runs in trade-only mode "
            "(DS' = M - X). Add QCL/FBS bulk downloads to enable full balance-sheet metrics.",
            directory,
        )
        return store

    for path in prod_files:
        try:
            raw = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
        except Exception as e:  # noqa: BLE001 - bad file shouldn't crash startup
            logger.warning("Failed to read FAOSTAT production file %s: %s", path.name, e)
            continue
        long_df = _normalise_long(raw, fbs=_is_fbs_frame(raw))
        if long_df is None:
            continue
        _accumulate_by_hs(long_df, _PRODUCTION_ELEMENTS, store.production)
        store.available = True

    for path in fbs_files:
        try:
            raw = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to read FAOSTAT FBS file %s: %s", path.name, e)
            continue
        long_df = _normalise_long(raw, fbs=True)
        if long_df is None:
            continue
        _accumulate_fbs_by_hs(long_df, _DOMESTIC_SUPPLY_ELEMENTS, store.domestic_supply)
        _accumulate_fbs_by_hs(long_df, _STOCK_VARIATION_ELEMENTS, store.stock_variation)
        # Population is country-level, not commodity-level.
        pop_rows = long_df[long_df["element"].map(lambda e: _match_element(e, _POPULATION_ELEMENTS))]
        for _, r in pop_rows.iterrows():
            people = float(r["value"]) * _THOUSAND  # FAOSTAT reports 1000 persons
            store.population_by_country[(int(r["m49"]), int(r["year"]))] = people
        store.available = True

    if fish_prod is not None:
        try:
            _accumulate_fishstat_production(fish_prod, fish_species, store.production)
            store.available = True
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to read FishStat production %s: %s", fish_prod.name, e)

    logger.info(
        "FAOSTAT store loaded: %d production keys, %d supply keys, %d stock-var keys, %d population keys",
        len(store.production), len(store.domestic_supply),
        len(store.stock_variation), len(store.population_by_country),
    )
    ch03 = sum(1 for k in store.production if str(k[0]).startswith("03"))
    if ch03:
        logger.info("  seafood (HS chapter 03) production keys: %d", ch03)
    return store


# ---------------------------------------------------------------------------
#  Backwards-compatible thin wrappers (used by older callers / scripts)
# ---------------------------------------------------------------------------

def load_production_data(path: Optional[str] = None) -> pd.DataFrame:
    """Return production as a tidy [commodity_hs, country_m49, period, production_kg] frame."""
    store = load_faostat_store(Path(path).parent if path else None)
    rows = [
        {"commodity_hs": hs, "country_m49": m49, "period": yr, "production_kg": kg}
        for (hs, m49, yr), kg in store.production.items()
    ]
    return pd.DataFrame(rows, columns=["commodity_hs", "country_m49", "period", "production_kg"])


def load_food_balance_sheets(path: Optional[str] = None) -> pd.DataFrame:
    """Return FBS supply/population as a tidy frame keyed by HS/country/period."""
    store = load_faostat_store(Path(path).parent if path else None)
    rows = []
    for (hs, m49, yr), kg in store.domestic_supply.items():
        rows.append({
            "commodity_hs": hs, "country_m49": m49, "period": yr,
            "domestic_supply_food_kg": kg,
            "population": store.population_by_country.get((m49, yr), float("nan")),
        })
    return pd.DataFrame(
        rows,
        columns=["commodity_hs", "country_m49", "period", "domestic_supply_food_kg", "population"],
    )
