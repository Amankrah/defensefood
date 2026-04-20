"""
RASFF (Rapid Alert System for Food and Feed) data ingestion.

Loads RASFF notifications from Excel, extracts corridors, and converts
to Rust-compatible RasffNotification objects for hazard signal modelling.

Corridor extraction rules (aligned with public RASFF Window + framework Sec. 4.1):

- `origin` can be a comma-separated list (e.g. "France,Ireland,Netherlands").
  Each origin produces its own set of corridors.

- Destinations are the union of four role columns, each carrying different
  operational meaning. We track which role(s) surfaced each destination so
  investigators can see WHY a country was flagged:

  * `notifying_country`   -- detected / reported the hazard (strong signal)
  * `distribution`        -- product was physically shipped there (strong signal)
  * `for_followUp` (ffup) -- must actively investigate, trace, and report back (strong)
  * `for_attention` (ffa) -- passively concerned (origin/transit); no action required
                             (weaker signal)

- `operator` is EXCLUDED. In RASFF terminology it represents the Food Business
  Operator (legal entity responsible for food law), not a destination country.
  In this dataset it frequently echoes the origin and would inflate corridors.

- Self-trade (origin == destination) is skipped; notifications where the
  notifying country is also the origin are common and don't produce a corridor.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from defensefood.ingestion.countries import get_m49_code


# Extract the category token(s) from the RASFF hazards column.
# Raw values look like: "norovirus   - {pathogenic micro-organisms}"
# or "Aflatoxin B1 - {mycotoxins},aflatoxin total - {mycotoxins}".
_HAZARD_CATEGORY_RE = re.compile(r"\{([^}]+)\}")


def _extract_hazard_categories(raw: object) -> str:
    """Return a comma-joined string of category tokens found in a hazards cell.

    Example input:  "Escherichia coli - {pathogenic micro-organisms}"
    Example output: "pathogenic micro-organisms"

    Multiple categories are preserved (comma-separated) so downstream parsers
    can decide how to map them. Falls back to the raw cell if no {...} token
    is present.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    matches = _HAZARD_CATEGORY_RE.findall(s)
    if matches:
        return ",".join(m.strip() for m in matches)
    # No brace-enclosed token: return raw so mapping logic can still try.
    return s


# Role-tagged destination columns.
# Order matters: the first role to list a country wins for display, but we
# accumulate ALL roles in destination_roles for diagnostic transparency.
# `operator` is deliberately absent -- it's the FBO, not a destination.
DESTINATION_ROLE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("notifying_country", "notifier"),
    ("distribution", "distribution"),
    ("for_followUp", "followUp"),
    ("for_attention", "attention"),
)

# Active-response roles: the destination actively handled / investigated / received
# the product. Used to distinguish "strong" corridor signal from passive mentions.
ACTIVE_ROLES: frozenset[str] = frozenset({"notifier", "distribution", "followUp"})


def _get_rasff_path() -> Path:
    """Resolve path to the RASFF Excel relative to this package."""
    return Path(__file__).resolve().parent.parent.parent / "updated_data_rasff_window.xlsx"


def load_rasff_data(path: Optional[Path] = None) -> pd.DataFrame:
    """Load the RASFF notification Excel file."""
    path = path or _get_rasff_path()
    if not path.exists():
        raise FileNotFoundError(f"RASFF Excel not found: {path}")
    return pd.read_excel(path)


def _parse_country_list(value) -> list[str]:
    """Split a comma-separated country string into a cleaned list.

    Handles NaN, empty, and whitespace. Returns [] when nothing usable.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return []
    return [c.strip() for c in s.split(",") if c.strip()]


def _collect_destinations(row: pd.Series) -> dict[int, dict]:
    """Union of mapped destination countries across DESTINATION_ROLE_COLUMNS.

    Returns: dict keyed by M49, each value carrying:
        - name: first-seen country name
        - roles: set of role tags (notifier/distribution/followUp/attention)
    """
    dests: dict[int, dict] = {}
    for col, role in DESTINATION_ROLE_COLUMNS:
        if col not in row.index:
            continue
        for name in _parse_country_list(row.get(col)):
            m49 = get_m49_code(name)
            if m49 is None:
                continue
            if m49 not in dests:
                dests[m49] = {"name": name, "roles": set()}
            dests[m49]["roles"].add(role)
    return dests


@dataclass
class Corridor:
    """A trade corridor derived from a RASFF notification.

    One notification can generate multiple corridors:
      - One per origin (when `origin` is comma-separated)
      - One per affected country (union of DESTINATION_ROLE_COLUMNS)

    `destination_roles` records which RASFF role(s) flagged the destination
    for this notification (e.g. {"distribution", "followUp"}). This lets
    investigators distinguish active response (ffup / notifier / distribution)
    from passive mentions (ffa only).
    """
    reference: str
    commodity_hs: str
    commodity_name: str
    origin_country: str
    origin_m49: int
    destination_country: str
    destination_m49: int
    destination_roles: frozenset[str] = frozenset()
    classification: str = ""
    risk_decision: str = ""
    hazard_category: str = ""
    period: int = 0  # YYYYMM

    @property
    def is_active_destination(self) -> bool:
        """True if the destination has an active-response role (not attention-only)."""
        return bool(self.destination_roles & ACTIVE_ROLES)


@dataclass
class RasffSummary:
    """Summary statistics from RASFF ingestion."""
    total_notifications: int = 0
    total_corridors: int = 0
    active_corridors: int = 0  # corridors with non-attention-only roles
    unique_origins: int = 0
    unique_destinations: int = 0
    unique_commodities: int = 0
    unmapped_origins: list[str] = field(default_factory=list)
    unmapped_destinations: list[str] = field(default_factory=list)
    notifications_without_origin: int = 0
    notifications_without_destination: int = 0
    self_trade_pairs_skipped: int = 0
    # Role distribution across corridors (for dashboards)
    role_counts: dict[str, int] = field(default_factory=dict)


def extract_corridors(df: Optional[pd.DataFrame] = None) -> tuple[list[Corridor], RasffSummary]:
    """Extract corridors from the RASFF DataFrame.

    For each notification row:
      1. Parse `origin` as a list (comma-separated allowed).
      2. Collect destinations from union of DESTINATION_ROLE_COLUMNS,
         tracking which role(s) flagged each country.
      3. Emit one Corridor per (origin, destination) pair, skipping self-trade.
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
    role_counts: dict[str, int] = {
        "notifier": 0, "distribution": 0, "followUp": 0, "attention": 0,
    }

    for _, row in df.iterrows():
        # ─── Origins (may be multi-valued) ─────────────────────────────
        origin_names = _parse_country_list(row.get("origin"))
        origins: list[tuple[str, int]] = []
        for name in origin_names:
            m49 = get_m49_code(name)
            if m49 is None:
                unmapped_origins.add(name)
                continue
            origins.append((name, m49))

        if not origins:
            summary.notifications_without_origin += 1
            continue

        # ─── Destinations with role tags ───────────────────────────────
        destinations = _collect_destinations(row)
        # Capture unmapped destination names for diagnostics
        for col, _ in DESTINATION_ROLE_COLUMNS:
            for name in _parse_country_list(
                row.get(col) if col in row.index else None
            ):
                if get_m49_code(name) is None:
                    unmapped_dests.add(name)

        if not destinations:
            summary.notifications_without_destination += 1
            continue

        # ─── Shared notification attributes ────────────────────────────
        raw_hs = row.get("hs_code")
        if pd.isna(raw_hs) or not raw_hs:
            hs_str = ""
        else:
            try:
                hs_str = str(int(float(raw_hs)))
            except (ValueError, TypeError):
                hs_str = str(raw_hs).strip()

        commodity_name = (
            str(row.get("commodities", "")) if pd.notna(row.get("commodities")) else ""
        )

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

        classification = (
            str(row.get("classification", "")) if pd.notna(row.get("classification")) else ""
        )
        risk_decision = (
            str(row.get("risk_decision", "")) if pd.notna(row.get("risk_decision")) else ""
        )
        # Public RASFF Window exports put hazard taxonomy in `hazards` as
        # "<agent> - {category}". Extract the {category} portion so our 6-way
        # taxonomy mapping (parse_hazard_type) has something to work with.
        hazard_raw = row.get("hazards") if "hazards" in df.columns else row.get("hazard_category")
        hazard_cat = _extract_hazard_categories(hazard_raw)
        reference = str(row.get("reference", ""))

        # ─── Cartesian product: (origin × destination) corridors ───────
        for origin_name, origin_m49 in origins:
            for dest_m49, dest_info in destinations.items():
                if origin_m49 == dest_m49:
                    summary.self_trade_pairs_skipped += 1
                    continue

                roles = frozenset(dest_info["roles"])
                unique_origins.add(origin_m49)
                unique_dests.add(dest_m49)
                if hs_str:
                    unique_commodities.add(hs_str)
                for r in roles:
                    role_counts[r] = role_counts.get(r, 0) + 1

                corridors.append(Corridor(
                    reference=reference,
                    commodity_hs=hs_str,
                    commodity_name=commodity_name,
                    origin_country=origin_name,
                    origin_m49=origin_m49,
                    destination_country=dest_info["name"],
                    destination_m49=dest_m49,
                    destination_roles=roles,
                    classification=classification,
                    risk_decision=risk_decision,
                    hazard_category=hazard_cat,
                    period=period,
                ))

    summary.total_corridors = len(corridors)
    summary.active_corridors = sum(1 for c in corridors if c.is_active_destination)
    summary.unique_origins = len(unique_origins)
    summary.unique_destinations = len(unique_dests)
    summary.unique_commodities = len(unique_commodities)
    summary.unmapped_origins = sorted(unmapped_origins)
    summary.unmapped_destinations = sorted(unmapped_dests)
    summary.role_counts = role_counts

    return corridors, summary
