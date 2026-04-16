"""
RASFF (Rapid Alert System for Food and Feed) data ingestion.

Loads RASFF notifications from Excel, extracts corridors, and converts
to Rust-compatible RasffNotification objects for hazard signal modelling.

Refactored from backend/script/country_loader.py with added hazard parsing.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from defensefood.ingestion.countries import get_m49_code


def _get_rasff_path() -> Path:
    """Resolve path to the RASFF Excel relative to this package."""
    return Path(__file__).resolve().parent.parent.parent / "updated_data_rasff_window.xlsx"


def load_rasff_data(path: Optional[Path] = None) -> pd.DataFrame:
    """Load the RASFF notification Excel file.

    Expected columns: reference, origin, for_followUp, hs_code, commodities,
    and optionally: classification, risk_decision, hazard_category, date.
    """
    path = path or _get_rasff_path()
    if not path.exists():
        raise FileNotFoundError(f"RASFF Excel not found: {path}")
    return pd.read_excel(path)


@dataclass
class Corridor:
    """A trade corridor derived from a RASFF notification.

    One notification can generate multiple corridors (one per affected country).
    """
    reference: str
    commodity_hs: str
    commodity_name: str
    origin_country: str
    origin_m49: int
    destination_country: str
    destination_m49: int
    classification: str = ""
    risk_decision: str = ""
    hazard_category: str = ""
    period: int = 0  # YYYYMM or YYYY


@dataclass
class RasffSummary:
    """Summary statistics from RASFF ingestion."""
    total_notifications: int = 0
    total_corridors: int = 0
    unique_origins: int = 0
    unique_destinations: int = 0
    unique_commodities: int = 0
    unmapped_origins: list[str] = field(default_factory=list)
    unmapped_destinations: list[str] = field(default_factory=list)


def extract_corridors(df: Optional[pd.DataFrame] = None) -> tuple[list[Corridor], RasffSummary]:
    """Extract corridors from RASFF DataFrame.

    Each notification row with an origin and one or more for_followUp countries
    produces one Corridor per affected country.

    Returns (corridors, summary).
    """
    if df is None:
        df = load_rasff_data()

    corridors: list[Corridor] = []
    summary = RasffSummary(total_notifications=len(df))
    unmapped_origins: set[str] = set()
    unmapped_dests: set[str] = set()
    unique_origins: set[int] = set()
    unique_dests: set[int] = set()
    unique_commodities: set[str] = set()

    for _, row in df.iterrows():
        origin = row.get("origin")
        if pd.isna(origin) or not origin:
            continue
        origin = str(origin).strip()
        origin_m49 = get_m49_code(origin)
        if origin_m49 is None:
            unmapped_origins.add(origin)
            continue

        follow_up = row.get("for_followUp")
        if pd.isna(follow_up) or not follow_up:
            continue

        # Parse HS code
        raw_hs = row.get("hs_code")
        if pd.isna(raw_hs) or not raw_hs:
            hs_str = ""
        else:
            try:
                hs_str = str(int(float(raw_hs)))
            except (ValueError, TypeError):
                hs_str = str(raw_hs).strip()

        commodity_name = str(row.get("commodities", "")) if pd.notna(row.get("commodities")) else ""

        # Parse date to period (YYYYMM or YYYY)
        period = 0
        date_val = row.get("date") or row.get("notification_date") or row.get("Date")
        if date_val is not None and not pd.isna(date_val):
            try:
                ts = pd.Timestamp(date_val)
                period = ts.year * 100 + ts.month  # YYYYMM
            except (ValueError, TypeError):
                try:
                    period = int(date_val)
                except (ValueError, TypeError):
                    pass

        classification = str(row.get("classification", "")) if pd.notna(row.get("classification")) else ""
        risk_decision = str(row.get("risk_decision", "")) if pd.notna(row.get("risk_decision")) else ""
        hazard_cat = str(row.get("hazard_category", "")) if pd.notna(row.get("hazard_category")) else ""

        # One corridor per affected country
        for country_str in str(follow_up).split(","):
            country_str = country_str.strip()
            if not country_str:
                continue
            dest_m49 = get_m49_code(country_str)
            if dest_m49 is None:
                unmapped_dests.add(country_str)
                continue

            unique_origins.add(origin_m49)
            unique_dests.add(dest_m49)
            if hs_str:
                unique_commodities.add(hs_str)

            corridors.append(Corridor(
                reference=str(row.get("reference", "")),
                commodity_hs=hs_str,
                commodity_name=commodity_name,
                origin_country=origin,
                origin_m49=origin_m49,
                destination_country=country_str,
                destination_m49=dest_m49,
                classification=classification,
                risk_decision=risk_decision,
                hazard_category=hazard_cat,
                period=period,
            ))

    summary.total_corridors = len(corridors)
    summary.unique_origins = len(unique_origins)
    summary.unique_destinations = len(unique_dests)
    summary.unique_commodities = len(unique_commodities)
    summary.unmapped_origins = sorted(unmapped_origins)
    summary.unmapped_destinations = sorted(unmapped_dests)

    return corridors, summary
