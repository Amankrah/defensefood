"""
Historical CVS materialisation — Phase 0 of the predictive epic.

The dependency_history dict on AppState carries Section 2 structural metrics
(BDI/OCS/HHI/IDR/SCI) per period, but does NOT carry CVS, HIS, or notification
counts per period. The predictive forecaster needs historical CVS as a
training label, so this module computes it once at startup.

How it works
------------

For each populated period in ``state.dependency_history``:

1. **Filter notifications to that period's vintage**: keep only RASFF rows
   whose ``period`` field (encoded as YYYY*100 + month) is ≤ year*100 + 12.
   This guarantees no future-leakage: if we score lane X for 2022, only
   notifications received on or before December 2022 count.
2. **Compute period-vintage HIS** via ``compute_corridor_hazard`` with the
   filtered notification list and ``current_period = year*100 + 12`` as the
   time-decay anchor.
3. **Merge** the Section 2 snapshot + the period-vintage hazard metrics +
   the (period-invariant) Section 3 CRS lookup + the Section 7 SCCS
   amplifier derived from per-period OCS.
4. **Run the full scoring pipeline** (normalise + compose) so every
   corridor in that period gets a normalised CVS comparable to the others
   in the same period.

The result is exposed as ``state.scored_history[period][lane_key]`` with
the same per-corridor shape as ``state.corridor_metrics`` but indexed by
trade year.

Caveats
-------

- **CRS is NOT per-period.** FAOSTAT FBS data shapes the consumption rank
  per (HS, destination); we use the latest FBS year as a static value
  across the back-test window. Lanes whose CRS comes online late will
  carry the static value historically, which is honest but worth knowing.
- **PAS amplifier (price anomaly) is skipped** in the historical pass —
  it's an optional Section 7 amplifier and computing it per period would
  add ~30% runtime. The two surviving amplifiers (HIS, SCCS) match what
  the lane brief uses today.
- **Single-period coverage is real**. Lanes whose trade rows only span one
  year of the corpus get one entry here. Training code skips them.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from defensefood.ingestion.hs_codes import normalize_hs
from defensefood.pipeline.hazard_pipeline import compute_corridor_hazard
from defensefood.pipeline.scoring_pipeline import run_scoring_pipeline

logger = logging.getLogger(__name__)


# Section 2 fields we copy from the per-period dependency snapshot into the
# per-period corridor dict before scoring. Mirrors ``_DEPENDENCY_FIELDS`` in
# dependencies.py.
_DEPENDENCY_FIELDS = (
    "ds_prime", "idr", "ocs", "bdi", "ssr", "hhi", "sci", "sci_norm",
    "provenance", "idr_gt_1", "bilateral_import_kg", "total_imports_kg",
    "production_kg",
)


def build_scored_history(state: Any) -> dict[int, dict[tuple[str, int, int], dict]]:
    """Materialise per-period scored corridor snapshots.

    Returns ``{trade_year: {(hs, dest, origin): scored_corridor_dict}}``.
    Every inner dict has at minimum: ``cvs``, ``cvs_mode``, ``his``,
    ``notification_count``, plus the merged Section 2 fields.

    Empty periods (years where the Section 2 pipeline failed) are skipped.
    Lanes that exist in a period's dependency snapshot but lack ``sci_norm``
    or ``his_norm`` after normalisation get ``cvs = None`` (no fabricated
    rank), matching the production scoring contract.
    """
    history = getattr(state, "dependency_history", None) or {}
    notifications = getattr(state, "notifications", None) or []
    config = getattr(state, "scoring_config", None)
    if config is None:
        from defensefood.models.scores import ScoringConfig
        config = ScoringConfig()

    crs_lookup = getattr(state, "crs_lookup", None) or {}

    # Build a corridor name lookup so the per-period dicts carry human
    # labels (commodity_name, country names). Pulls from corridor_metrics
    # which is already enriched at startup.
    name_lookup: dict[tuple[str, int, int], dict[str, str]] = {}
    for m in getattr(state, "corridor_metrics", None) or []:
        try:
            key = (
                m["commodity_hs"],
                int(m["destination_m49"]),
                int(m["origin_m49"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        name_lookup[key] = {
            "commodity_name": m.get("commodity_name") or "",
            "destination_country": m.get("destination_country") or "",
            "origin_country": m.get("origin_country") or "",
            "market_presence": m.get("market_presence") or "",
        }

    out: dict[int, dict[tuple[str, int, int], dict]] = {}

    for period, dep_snapshot in history.items():
        if not isinstance(dep_snapshot, dict) or not dep_snapshot:
            continue
        period_int = int(period)
        # December of the trade year as the time-decay anchor for HIS.
        cutoff_yyyymm = period_int * 100 + 12
        period_notifs = [
            n for n in notifications
            if int(getattr(n, "period", 0) or 0) <= cutoff_yyyymm
        ]

        corridors_for_period: list[dict[str, Any]] = []
        for key, dep_metrics in dep_snapshot.items():
            if not isinstance(dep_metrics, dict) or "error" in dep_metrics:
                continue
            try:
                hs, dest, origin = key
                dest = int(dest)
                origin = int(origin)
            except (TypeError, ValueError):
                continue

            # Section 4 — vintage HIS for this period.
            try:
                haz = compute_corridor_hazard(
                    period_notifs,
                    hs,
                    dest,
                    origin,
                    current_period=cutoff_yyyymm,
                    alpha=getattr(config, "alpha_decay", 0.9),
                )
            except Exception as exc:  # noqa: BLE001 - hazard is best-effort
                logger.debug(
                    "compute_corridor_hazard failed for %s in %s: %s",
                    key, period_int, exc,
                )
                haz = {
                    "his": None,
                    "hdi": None,
                    "notification_count": 0,
                    "severity_total": 0.0,
                    "hazard_breakdown": {},
                }

            entry: dict[str, Any] = {
                "commodity_hs": hs,
                "destination_m49": dest,
                "origin_m49": origin,
                "period": period_int,
            }
            # Copy commodity/country labels for downstream display.
            entry.update(name_lookup.get((hs, dest, origin), {}))
            # Section 2 dependency fields.
            for f in _DEPENDENCY_FIELDS:
                if f in dep_metrics:
                    entry[f] = dep_metrics[f]
            # Section 4 hazard fields (period-vintage).
            for f in ("his", "hdi", "notification_count", "severity_total"):
                entry[f] = haz.get(f)
            # Section 3 — CRS is static; period-invariant FBS data. Use the
            # latest-period lookup as a "best available" historical value.
            consumption_key = (normalize_hs(hs), dest)
            crs = crs_lookup.get(consumption_key)
            if crs is not None:
                entry["crs"] = crs
            # Section 7 — SCCS amplifier from per-period OCS.
            ocs = entry.get("ocs")
            if ocs is not None:
                try:
                    entry["sccs"] = 1.0 - float(ocs)
                except (TypeError, ValueError):
                    pass

            corridors_for_period.append(entry)

        if not corridors_for_period:
            continue

        scored = run_scoring_pipeline(corridors_for_period, config)
        out[period_int] = {
            (c["commodity_hs"], int(c["destination_m49"]), int(c["origin_m49"])): c
            for c in scored
        }

    logger.info(
        "scored_history built: %d periods, %d total scored corridors",
        len(out),
        sum(len(snap) for snap in out.values()),
    )

    return out


def coverage_summary(
    scored_history: dict[int, dict[tuple[str, int, int], dict]]
) -> dict[str, Any]:
    """Quick stats about the materialised history: periods, counts per period,
    fraction of corridors with non-null CVS. Useful for the CLI and tests.
    """
    per_period: list[dict[str, Any]] = []
    for period in sorted(scored_history.keys()):
        snap = scored_history[period]
        total = len(snap)
        with_cvs = sum(1 for c in snap.values() if c.get("cvs") is not None)
        per_period.append(
            {
                "period": period,
                "corridors": total,
                "with_cvs": with_cvs,
                "cvs_coverage": (with_cvs / total) if total else 0.0,
            }
        )
    return {
        "periods": [r["period"] for r in per_period],
        "by_period": per_period,
        "total_lane_periods": sum(r["corridors"] for r in per_period),
    }


def lane_history(
    scored_history: dict[int, dict[tuple[str, int, int], dict]],
    lane_key: tuple[str, int, int],
) -> list[dict[str, Any]]:
    """Return the per-period entries for one lane, sorted ascending by period.

    Lanes that exist in some periods but not others get a sparse list; the
    forecaster's feature extractor handles holes.
    """
    out: list[dict[str, Any]] = []
    for period in sorted(scored_history.keys()):
        entry = scored_history[period].get(lane_key)
        if entry is not None:
            out.append(entry)
    return out


__all__ = ["build_scored_history", "coverage_summary", "lane_history"]
