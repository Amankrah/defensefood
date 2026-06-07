"""
Shared FastAPI dependencies.

Provides singleton access to data and pipeline results
that are loaded once at startup and shared across requests.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from defensefood_core import RasffNotification
from defensefood.ingestion.comtrade import load_merged_trade_data
from defensefood.ingestion.faostat import FaostatStore, load_faostat_store
from defensefood.ingestion.hs_codes import normalize_hs
from defensefood.ingestion.rasff import Corridor, RasffSummary, extract_corridors, load_rasff_data
from defensefood.models.scores import ScoringConfig
from defensefood.pipeline.consumption_pipeline import compute_consumption_lookups
from defensefood.pipeline.data_quality import count_by_reason
from defensefood.pipeline.dependency_pipeline import run_dependency_pipeline
from defensefood.pipeline.hazard_pipeline import (
    build_notifications,
    compute_corridor_hazard,
    compute_dgi_for_corridor,
)

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
    # Predictive epic Phase 0:
    # scored_history[period][(hs, dest, origin)] -> per-period scored corridor
    # dict including CVS, HIS, notification_count, plus the merged Section 2
    # fields. Materialised by build_scored_history() after dependency_history
    # is in place. Lanes with one period only get one entry.
    scored_history: dict[int, dict[tuple[str, int, int], dict]] = field(default_factory=dict)
    # Predictive epic Phase 3:
    # Fitted forecaster trained on every period EXCEPT the latest, so it
    # can predict the next period from the latest. None when training
    # failed or lightgbm isn't installed.
    forecaster: Optional[Any] = None
    # The period the forecaster predicts (latest + 1).
    forecast_target_period: int = 0
    # notifications_by_corridor[(commodity_hs, dest_m49, origin_m49)] -> list of raw RASFF rows
    notifications_by_corridor: dict[tuple[str, int, int], list[dict]] = field(default_factory=dict)
    # coverage: data-quality / coverage diagnostics
    coverage: dict = field(default_factory=dict)
    # Section 3 lookups by (hs, destination_m49) -> value. Populated alongside dependency.
    pcc_lookup: dict[tuple[str, int], float] = field(default_factory=dict)
    crs_lookup: dict[tuple[str, int], float] = field(default_factory=dict)
    dis_lookup: dict[tuple[str, int], float] = field(default_factory=dict)
    # Section 6.4 (Eq. 35): m̄(c) — average shipment size (kg) per HS-2 chapter.
    # Built once from the trade DataFrame at startup; falls back to "global" key.
    avg_shipment_lookup: dict[str, float] = field(default_factory=dict)


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

    # Section 6.4 m̄(c) lookup — built once from the loaded trade table.
    from defensefood.pipeline.network_pipeline import (
        estimate_avg_shipment_size_by_hs_chapter,
    )
    state.avg_shipment_lookup = estimate_avg_shipment_size_by_hs_chapter(state.trade_df)

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
        from defensefood.ingestion.rasff import ACTIVE_ROLES, market_presence_from_roles
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
                alpha=state.scoring_config.alpha_decay,
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
            metrics["market_presence"] = market_presence_from_roles(roles)

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

    # Section 3 in one pass — PCC (kg/capita/yr), CRS (rank), DIS (inelasticity).
    pcc_lookup, crs_lookup, dis_lookup = compute_consumption_lookups(
        state.faostat, trade_period or None
    )
    # Cache lookups on state so the network / ORPS / ACEP path can read them too.
    state.pcc_lookup = pcc_lookup
    state.crs_lookup = crs_lookup
    state.dis_lookup = dis_lookup

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
        consumption_key = (hs_norm, m["destination_m49"])
        pcc = pcc_lookup.get(consumption_key)
        if pcc is not None:
            m["pcc"] = pcc
        crs = crs_lookup.get(consumption_key)
        if crs is not None:
            m["crs"] = crs
        dis = dis_lookup.get(consumption_key)
        if dis is not None:
            m["dis"] = dis

        # Section 7 amplifier — SCCS = 1 - OCS (percentile-ranked downstream).
        # Reads as "this single origin is a small slice of the destination's
        # import mix → more middlemen, more complexity in the supply chain".
        ocs = m.get("ocs")
        if ocs is not None:
            m["sccs"] = 1.0 - float(ocs)

    # ── Section 4.5 Detection Gap Indicator ────────────────────────────────
    # DGI = trade_share − notification_share. Computed per corridor where the
    # destination has both bilateral trade and at least one origin-attributable
    # notification for the commodity; NaN/None otherwise.
    dgi_count = 0
    if state.notifications:
        for m in state.corridor_metrics:
            bilateral = m.get("bilateral_import_kg") or 0.0
            total_imp = m.get("total_imports_kg") or 0.0
            if bilateral <= 0 or total_imp <= 0:
                continue
            dgi = compute_dgi_for_corridor(
                state.notifications,
                m["commodity_hs"],
                m["destination_m49"],
                m["origin_m49"],
                float(bilateral),
                float(total_imp),
            )
            # Engine returns NaN when no notifications match — skip those.
            if dgi == dgi:  # not NaN
                m["dgi"] = dgi
                dgi_count += 1

    # ── Section 7 PAS amplifier — Price Anomaly Score ─────────────────────
    # PAS = min(|z_uv|, 3.0); percentile-ranked across the corpus when the
    # scoring pipeline normalises. Built once from a single pass over the
    # trade DataFrame at the same year used for dependency enrichment.
    pas_count = 0
    if trade_period is not None and state.trade_df is not None and not state.trade_df.empty:
        from defensefood.pipeline.trade_flow_pipeline import (
            compute_unit_value_anomalies_for_all_corridors,
        )
        z_uv_lookup = compute_unit_value_anomalies_for_all_corridors(
            state.trade_df, int(trade_period),
        )
        for m in state.corridor_metrics:
            key = (
                str(m.get("commodity_hs", "")),
                int(m.get("destination_m49") or 0),
                int(m.get("origin_m49") or 0),
            )
            z = z_uv_lookup.get(key)
            if z is None:
                continue
            m["z_uv"] = z
            m["pas"] = min(abs(z), 3.0)
            pas_count += 1

    logger.info(
        "Dependency enrichment: %d/%d corridors got Section 2 metrics (period=%s, faostat=%s); "
        "Section 3 lookups: %d PCC keys, %d CRS keys, %d DIS keys; "
        "Section 4.5 DGI populated for %d corridors; "
        "Section 7 PAS populated for %d corridors",
        enriched, len(state.corridor_metrics), trade_period,
        bool(state.faostat and state.faostat.available),
        len(pcc_lookup), len(crs_lookup), len(dis_lookup),
        dgi_count, pas_count,
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

    # Phase 0 of the predictive epic — materialise per-period CVS / HIS so
    # downstream forecasters and the back-test harness have a training
    # label. Builds on top of dependency_history that was just populated.
    from defensefood.agent.predictive.historical_snapshots import (
        build_scored_history,
    )
    try:
        state.scored_history = build_scored_history(state)
    except Exception as exc:  # noqa: BLE001 - never block startup on this
        logger.warning("build_scored_history failed: %s", exc)
        state.scored_history = {}

    # Phase 3 of the predictive epic — train the production forecaster on
    # every period except the latest so we can predict the latest + 1 at
    # request time. Wrapped in try/except so a missing dependency or a
    # degenerate training set never blocks startup. The agent tool and
    # HTTP endpoint check ``state.forecaster is None`` and report
    # ``predictive_unavailable`` gracefully when training was skipped.
    #
    # Production model = PERSISTENCE.
    # The 2026-06-07 backtest (5 walks, 3503 labelled cases) showed
    # persistence MAE 0.0215 vs LightGBM MAE 0.0249 — LightGBM 15.8% worse,
    # and LightGBM's 80% interval covered only 56% of actuals (severely
    # overconfident). Persistence covered 83% — near-perfect calibration.
    # LightGBM remains available via ``python -m script.predictive backtest
    # --forecaster lightgbm`` for further experimentation; the production
    # ForecastCard + anomaly_explainer model_outlook use persistence.
    PRODUCTION_FORECASTER = "persistence"

    populated_periods = sorted(
        p for p, snap in state.scored_history.items()
        if isinstance(snap, dict) and snap
    )
    if len(populated_periods) >= 2:
        try:
            from defensefood.agent.predictive import build_forecaster
            from defensefood.agent.predictive.eval_harness import prepare_forecaster

            forecaster = build_forecaster(PRODUCTION_FORECASTER, state=state)
            train_periods = populated_periods[:-1]
            prepare_forecaster(
                state, forecaster=forecaster, train_periods=train_periods
            )
            state.forecaster = forecaster
            state.forecast_target_period = populated_periods[-1] + 1
            logger.info(
                "Predictive forecaster ready: target_period=%d, "
                "train_periods=%s, model=%s",
                state.forecast_target_period,
                train_periods,
                PRODUCTION_FORECASTER,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Forecaster training failed at startup (%s); predict tool "
                "will report 'predictive_unavailable'.",
                exc,
            )

    refresh_coverage(state)

    logger.info(
        "Research indices built: %d corridors with raw notifications, "
        "%d dependency-history periods, %d scored-history periods, "
        "%d/%d corridors FAOSTAT-tagged",
        len(nbc), len(history), len(state.scored_history),
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
    by_quality = {
        tier: sum(1 for m in state.corridor_metrics if m.get("data_quality") == tier)
        for tier in ("full", "hazard_only", "partial", "unavailable")
    }

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
        "corridors_by_data_quality": by_quality,
        "sci_unavailable_by_reason": count_by_reason(state.corridor_metrics),
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
