"""
Shared FastAPI dependencies.

Provides singleton access to data and pipeline results
that are loaded once at startup and shared across requests.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from defensefood_core import RasffNotification
from defensefood.ingestion.comtrade import load_merged_trade_data
from defensefood.ingestion.faostat import FaostatStore, load_faostat_store
from defensefood.ingestion.hs_codes import normalize_hs
from defensefood.ingestion.rasff import Corridor, RasffSummary, extract_corridors, load_rasff_data
from defensefood.models.scores import ScoringConfig
from defensefood.pipeline.consumption_pipeline import compute_crs_lookup
from defensefood.pipeline.dependency_pipeline import run_dependency_pipeline
from defensefood.pipeline.hazard_pipeline import build_notifications, compute_corridor_hazard

logger = logging.getLogger(__name__)

# Dependency / consumption fields copied onto each corridor metric at startup.
_DEPENDENCY_FIELDS = (
    "ds_prime", "idr", "ocs", "bdi", "ssr", "hhi", "sci", "sci_norm",
    "provenance", "idr_gt_1", "bilateral_import_kg", "total_imports_kg",
    "production_kg",
)


@dataclass
class AppState:
    """Application-wide state loaded at startup."""
    trade_df: Optional[pd.DataFrame] = None
    rasff_df: Optional[pd.DataFrame] = None
    corridors: list[Corridor] = field(default_factory=list)
    rasff_summary: Optional[RasffSummary] = None
    notifications: list[RasffNotification] = field(default_factory=list)
    corridor_metrics: list[dict] = field(default_factory=list)
    scoring_config: ScoringConfig = field(default_factory=ScoringConfig)
    current_period: int = 0
    faostat: Optional[FaostatStore] = None
    trade_period: int = 0
    # Research mode state -- populated once at startup.
    # dependency_history[period][(commodity_hs, dest_m49, origin_m49)] -> metric dict
    dependency_history: dict[int, dict[tuple[str, int, int], dict]] = field(default_factory=dict)
    # notifications_by_corridor[(commodity_hs, dest_m49, origin_m49)] -> list of raw RASFF rows
    notifications_by_corridor: dict[tuple[str, int, int], list[dict]] = field(default_factory=dict)
    # coverage: data-quality / coverage diagnostics
    coverage: dict = field(default_factory=dict)


_state: Optional[AppState] = None


def get_state() -> AppState:
    """Get the global app state (lazy-initialized)."""
    global _state
    if _state is None:
        _state = AppState()
        _load_data(_state)
    return _state


def _load_data(state: AppState) -> None:
    """Load all data sources into app state."""
    # Load trade data
    try:
        state.trade_df = load_merged_trade_data()
    except FileNotFoundError:
        logger.warning(
            "Merged trade file not found; API will serve empty trade data. "
            "Run ingestion or place merged Comtrade output where load_merged_trade_data expects it."
        )
        state.trade_df = pd.DataFrame()

    # Load RASFF data and run hazard pipeline
    try:
        state.rasff_df = load_rasff_data()
        state.corridors, state.rasff_summary = extract_corridors(state.rasff_df)
        state.notifications = build_notifications(state.corridors)

        # Determine current period
        periods = [n.period for n in state.notifications if n.period > 0]
        state.current_period = max(periods) if periods else 202600

        # Build reference -> hazard category string map so HDI can count
        # every category a notification lists (not just the first).
        from defensefood.ingestion.rasff import _extract_hazard_categories
        hazard_category_map: dict[str, str] = {}
        for c in state.corridors:
            if c.reference and c.reference not in hazard_category_map:
                hazard_category_map[c.reference] = c.hazard_category

        # Aggregate destination roles per corridor across notifications
        from defensefood.ingestion.rasff import ACTIVE_ROLES
        roles_by_corridor: dict[tuple[str, int, int], set[str]] = {}
        role_counts_by_corridor: dict[tuple[str, int, int], dict[str, int]] = {}
        for c in state.corridors:
            key = (c.commodity_hs, c.destination_m49, c.origin_m49)
            if key not in roles_by_corridor:
                roles_by_corridor[key] = set()
                role_counts_by_corridor[key] = {
                    "notifier": 0, "distribution": 0,
                    "followUp": 0, "attention": 0,
                }
            for r in c.destination_roles:
                roles_by_corridor[key].add(r)
                role_counts_by_corridor[key][r] += 1

        # Compute hazard metrics for each unique corridor
        seen = set()
        for c in state.corridors:
            key = (c.commodity_hs, c.destination_m49, c.origin_m49)
            if key in seen or not c.commodity_hs:
                continue
            seen.add(key)

            metrics = compute_corridor_hazard(
                state.notifications, c.commodity_hs, c.destination_m49,
                c.origin_m49, state.current_period,
                hazard_category_map=hazard_category_map,
            )
            metrics["commodity_hs"] = c.commodity_hs
            metrics["commodity_name"] = c.commodity_name
            metrics["destination_m49"] = c.destination_m49
            metrics["destination_country"] = c.destination_country
            metrics["origin_m49"] = c.origin_m49
            metrics["origin_country"] = c.origin_country

            roles = roles_by_corridor.get(key, set())
            metrics["destination_roles"] = sorted(roles)
            metrics["role_counts"] = role_counts_by_corridor.get(key, {})
            metrics["is_active_destination"] = bool(roles & ACTIVE_ROLES)

            state.corridor_metrics.append(metrics)

        _enrich_dependency_consumption(state)
        _build_research_indices(state)

    except FileNotFoundError:
        logger.warning(
            "RASFF data file not found; corridor metrics and hazard summaries will be empty."
        )


def _enrich_dependency_consumption(state: AppState) -> None:
    """Attach Section 2 (dependency) and Section 3 (CRS) metrics to every corridor.

    Runs once at startup so list/sort endpoints and CVS scoring see SCI/IDR/etc.
    without per-request recomputation. Uses the latest trade YEAR (not the RASFF
    YYYYMM period). FAOSTAT supplies P/D when present; otherwise dependency runs
    in trade-only mode (DS' = M - X) and CRS is simply absent.
    """
    state.faostat = load_faostat_store()

    trade_period = 0
    dep: dict = {}
    if state.trade_df is not None and not state.trade_df.empty:
        trade_period = int(sorted(state.trade_df["period"].astype(int).unique())[-1])
        keys = [
            (m["commodity_hs"], m["destination_m49"], m["origin_m49"])
            for m in state.corridor_metrics
        ]
        dep = run_dependency_pipeline(state.trade_df, keys, state.faostat, trade_period)
    state.trade_period = trade_period

    crs_lookup = compute_crs_lookup(state.faostat, trade_period or None)

    enriched = 0
    for m in state.corridor_metrics:
        key = (m["commodity_hs"], m["destination_m49"], m["origin_m49"])
        d = dep.get(key)
        if d and "error" not in d:
            for f in _DEPENDENCY_FIELDS:
                if f in d:
                    m[f] = d[f]
            enriched += 1
        elif d and "error" in d:
            m["dependency_error"] = d["error"]

        hs_norm = normalize_hs(m["commodity_hs"])
        crs = crs_lookup.get((hs_norm, m["destination_m49"]))
        if crs is not None:
            m["crs"] = crs

    logger.info(
        "Dependency enrichment: %d/%d corridors got Section 2 metrics (period=%s, faostat=%s); "
        "%d destinations have CRS",
        enriched, len(state.corridor_metrics), trade_period,
        bool(state.faostat and state.faostat.available), len(crs_lookup),
    )


def _build_research_indices(state: AppState) -> None:
    """Populate the research-mode state: per-period dependency snapshots,
    raw-notification index by corridor, and a coverage summary.

    All read-only, additive — the planner-mode state computed above is
    untouched. Runs once at startup.
    """
    from defensefood.core import HazardEngine, parse_classification, parse_risk_decision

    # ── notifications_by_corridor ──────────────────────────────────────
    # Each Corridor row already carries the raw RASFF fields the researcher
    # cares about (reference, period, classification, risk_decision,
    # hazard_category, destination_roles). Compute severity_weight per row so
    # the researcher can see exactly what fed into HIS.
    nbc: dict[tuple[str, int, int], list[dict]] = {}
    for c in state.corridors:
        if not c.commodity_hs:
            continue
        key = (c.commodity_hs, c.destination_m49, c.origin_m49)
        try:
            sev = HazardEngine.severity(
                parse_classification(c.classification),
                parse_risk_decision(c.risk_decision),
            )
        except Exception:  # noqa: BLE001 - severity computation is best-effort
            sev = 0.0
        nbc.setdefault(key, []).append(
            {
                "reference": c.reference,
                "period": c.period,
                "classification": c.classification,
                "risk_decision": c.risk_decision,
                "hazard_category": c.hazard_category,
                "destination_roles": sorted(c.destination_roles),
                "severity_weight": sev,
            }
        )
    # De-duplicate by reference within a lane (a single notification can map
    # to multiple rows when several destinations are listed).
    for key, rows in nbc.items():
        seen: set[str] = set()
        deduped: list[dict] = []
        for r in rows:
            if r["reference"] and r["reference"] in seen:
                continue
            seen.add(r["reference"])
            deduped.append(r)
        nbc[key] = sorted(deduped, key=lambda r: -int(r.get("period") or 0))
    state.notifications_by_corridor = nbc

    # ── dependency_history ─────────────────────────────────────────────
    # Re-run the Section 2 pipeline for every distinct trade year so the
    # researcher can see how IDR/OCS/HHI/SCI moved period to period.
    history: dict[int, dict[tuple[str, int, int], dict]] = {}
    if state.trade_df is not None and not state.trade_df.empty:
        periods = sorted({int(p) for p in state.trade_df["period"].astype(int).unique()})
        keys = [
            (m["commodity_hs"], m["destination_m49"], m["origin_m49"])
            for m in state.corridor_metrics
        ]
        for p in periods:
            try:
                history[p] = run_dependency_pipeline(state.trade_df, keys, state.faostat, p)
            except Exception as e:  # noqa: BLE001
                logger.warning("Dependency history pass failed for period %s: %s", p, e)
                history[p] = {}
    state.dependency_history = history

    refresh_coverage(state)

    logger.info(
        "Research indices built: %d corridors with raw notifications, "
        "%d dependency-history periods, %d/%d corridors FAOSTAT-tagged",
        len(nbc), len(history),
        state.coverage.get("corridors_faostat", 0),
        state.coverage.get("corridors_total", 0),
    )


def refresh_coverage(state: AppState) -> None:
    """Recompute the coverage diagnostics from current corridor_metrics.

    Called once from `_build_research_indices` and again from the API lifespan
    after CVS scoring runs, so the cvs-count reflects post-scoring state.
    """
    n_corr = len(state.corridor_metrics)
    n_faostat = sum(1 for m in state.corridor_metrics if m.get("provenance") == "faostat")
    n_cvs = sum(1 for m in state.corridor_metrics if m.get("cvs") is not None)
    n_with_dep = sum(1 for m in state.corridor_metrics if m.get("sci") is not None)
    n_with_crs = sum(1 for m in state.corridor_metrics if m.get("crs") is not None)
    n_idr_gt_1 = sum(1 for m in state.corridor_metrics if m.get("idr_gt_1"))

    summary = state.rasff_summary
    unmapped_origins = list(summary.unmapped_origins) if summary else []
    unmapped_dests = list(summary.unmapped_destinations) if summary else []

    by_chapter: dict[str, dict[str, int]] = {}
    for m in state.corridor_metrics:
        hs = str(m.get("commodity_hs", ""))
        chapter = hs[:2] if len(hs) >= 2 else "??"
        bucket = by_chapter.setdefault(
            chapter, {"total": 0, "faostat": 0, "trade_only": 0, "no_trade": 0}
        )
        bucket["total"] += 1
        prov = m.get("provenance")
        if prov == "faostat":
            bucket["faostat"] += 1
        elif prov == "trade_only":
            bucket["trade_only"] += 1
        else:
            bucket["no_trade"] += 1

    trade_periods: list[int] = []
    if state.trade_df is not None and not state.trade_df.empty:
        trade_periods = sorted({int(p) for p in state.trade_df["period"].astype(int).unique()})

    rasff_periods = sorted({n.period for n in state.notifications if n.period > 0})

    state.coverage = {
        "corridors_total": n_corr,
        "corridors_faostat": n_faostat,
        "corridors_with_dependency": n_with_dep,
        "corridors_with_crs": n_with_crs,
        "corridors_with_cvs": n_cvs,
        "corridors_idr_gt_1": n_idr_gt_1,
        "unmapped_origins": unmapped_origins,
        "unmapped_destinations": unmapped_dests,
        "trade_periods": trade_periods,
        "rasff_periods_count": len(rasff_periods),
        "rasff_period_min": min(rasff_periods) if rasff_periods else None,
        "rasff_period_max": max(rasff_periods) if rasff_periods else None,
        "by_hs_chapter": [
            {"chapter": ch, **counts}
            for ch, counts in sorted(by_chapter.items(), key=lambda x: -x[1]["total"])
        ],
        "faostat_available": bool(state.faostat and state.faostat.available),
    }


def reload_data() -> AppState:
    """Force reload all data sources."""
    global _state
    _state = AppState()
    _load_data(_state)
    return _state
