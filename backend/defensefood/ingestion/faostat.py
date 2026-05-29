"""
FAOSTAT data ingestion -- production (P), domestic supply (D), population.

Feeds the dependency (Section 2) and consumption (Section 3) models with the
balance-sheet quantities the framework's worked examples assume.

Data source: FAOSTAT bulk-download CSVs (the "All Data Normalized" long format).
Two domains are used:

  * QCL  -- "Crops and livestock products"  -> Element "Production"
  * FBS  -- "Food Balance Sheets"           -> Elements "Domestic supply
            quantity", "Food supply quantity (kg/capita/yr)",
            "Total Population - Both sexes"

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
from pathlib import Path
from typing import Optional

import pandas as pd

from defensefood.ingestion.hs_codes import cpc_for_hs, normalize_cpc

logger = logging.getLogger(__name__)

# FAOSTAT element labels we care about (lower-cased, matched as substrings so
# minor wording/case differences across releases still resolve).
_PRODUCTION_ELEMENTS = ("production",)
_DOMESTIC_SUPPLY_ELEMENTS = ("domestic supply quantity",)
_POPULATION_ELEMENTS = ("total population - both sexes", "total population")

# Column-name candidates across FAOSTAT releases.
_COL_CANDIDATES = {
    "area_m49": ("Area Code (M49)", "Area Code M49", "Area Code"),
    "item_cpc": ("Item Code (CPC)", "Item Code CPC", "Item Code"),
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


def _find_files(directory: Path, *keywords: str) -> list[Path]:
    """CSV files in `directory` whose name contains any keyword (case-insensitive)."""
    if not directory.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(directory.glob("*.csv")):
        name = p.name.lower()
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


def _normalise_long(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Reduce a raw FAOSTAT bulk frame to [cpc, m49, year, element, unit, value]."""
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
    out["cpc"] = df[cols["item_cpc"]].map(normalize_cpc) if cols["item_cpc"] else None
    out["unit"] = df[cols["unit"]].astype(str).str.strip().str.lower() if cols["unit"] else ""
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
    """
    production: dict[tuple[str, int, int], float] = field(default_factory=dict)
    domestic_supply: dict[tuple[str, int, int], float] = field(default_factory=dict)
    population_by_country: dict[tuple[int, int], float] = field(default_factory=dict)
    available: bool = False

    def production_kg(self, hs: str, m49: int, year: int) -> Optional[float]:
        return self.production.get((hs, m49, year))

    def domestic_supply_kg(self, hs: str, m49: int, year: int) -> Optional[float]:
        return self.domestic_supply.get((hs, m49, year))

    def population(self, m49: int, year: int) -> Optional[float]:
        return self.population_by_country.get((m49, year))


def _accumulate_by_hs(
    long_df: pd.DataFrame,
    wanted_elements: tuple[str, ...],
    target: dict[tuple[str, int, int], float],
) -> None:
    """Sum CPC-keyed values into an HS-keyed dict via the concordance."""
    rows = long_df[long_df["element"].map(lambda e: _match_element(e, wanted_elements))]
    # Precompute CPC -> [HS] from the concordance lazily per CPC seen.
    cpc_to_hs_cache: dict[str, list[str]] = {}
    from defensefood.ingestion.hs_codes import load_hs_cpc_concordance
    conc = load_hs_cpc_concordance()
    for cpc, grp in conc.groupby("cpc"):
        cpc_to_hs_cache[cpc] = sorted(set(grp["hs"]))

    for _, r in rows.iterrows():
        cpc = r["cpc"]
        if cpc is None or cpc not in cpc_to_hs_cache:
            continue
        kg = _value_to_kg(float(r["value"]), r["unit"])
        m49, year = int(r["m49"]), int(r["year"])
        for hs in cpc_to_hs_cache[cpc]:
            key = (hs, m49, year)
            target[key] = target.get(key, 0.0) + kg


def load_faostat_store(data_dir: Optional[Path] = None) -> FaostatStore:
    """Build the FAOSTAT lookup store from bulk CSVs in the data directory.

    Returns an empty (available=False) store when no files are found, so the
    rest of the pipeline keeps working in trade-only mode.
    """
    directory = _faostat_dir(data_dir)
    store = FaostatStore()

    prod_files = _find_files(directory, "production", "qcl")
    fbs_files = _find_files(directory, "food_balance", "foodbalance", "fbs")

    if not prod_files and not fbs_files:
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
        long_df = _normalise_long(raw)
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
        long_df = _normalise_long(raw)
        if long_df is None:
            continue
        _accumulate_by_hs(long_df, _DOMESTIC_SUPPLY_ELEMENTS, store.domestic_supply)
        # Population is country-level, not commodity-level.
        pop_rows = long_df[long_df["element"].map(lambda e: _match_element(e, _POPULATION_ELEMENTS))]
        for _, r in pop_rows.iterrows():
            people = float(r["value"]) * _THOUSAND  # FAOSTAT reports 1000 persons
            store.population_by_country[(int(r["m49"]), int(r["year"]))] = people
        store.available = True

    logger.info(
        "FAOSTAT store loaded: %d production keys, %d supply keys, %d population keys",
        len(store.production), len(store.domestic_supply), len(store.population_by_country),
    )
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
