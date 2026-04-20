"""
Scoring Pipeline -- Section 7 computation orchestration.

Normalises sub-scores from all prior sections and composes them into
the final Composite Vulnerability Score (CVS) per corridor.

Missing inputs are handled honestly: a corridor without structural data
(SCI / CRS) does NOT get a fabricated low rank; it stays NaN through
normalisation and receives `cvs = None`. This prevents the dashboard
from sorting corridors into meaningful-looking orders based purely on
missing-data artefacts.
"""

import math
from typing import Optional

import numpy as np

from defensefood.core import ScoringEngine
from defensefood.models.scores import CompositionMethod, ScoringConfig


def _coerce(value) -> float:
    """Convert None / None-ish to NaN, otherwise float()."""
    if value is None:
        return float("nan")
    try:
        f = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return f


def normalise_corridor_scores(
    corridors: list[dict],
    config: Optional[ScoringConfig] = None,
) -> list[dict]:
    """Normalise raw sub-scores across all corridors.

    Missing / non-numeric values become NaN and the Rust normalisers leave
    them as NaN. Downstream consumers can skip them or render "N/A".
    """
    if config is None:
        config = ScoringConfig()

    method = config.normalisation_method.value
    keys_to_normalise = ["sci", "his", "crs"]

    raw_arrays = {}
    for key in keys_to_normalise:
        values = [_coerce(c.get(key)) for c in corridors]
        raw_arrays[key] = np.array(values, dtype=float)

    norm_arrays = {}
    for key, arr in raw_arrays.items():
        if key == "his" and method != "log_percentile":
            # Framework Sec. 7.1.3: HIS follows an exponential distribution;
            # log-percentile is the recommended normalisation.
            norm_arrays[key] = ScoringEngine.normalise(arr, "log_percentile")
        else:
            norm_arrays[key] = ScoringEngine.normalise(arr, method)

    for i, c in enumerate(corridors):
        for key in keys_to_normalise:
            v = float(norm_arrays[key][i])
            c[f"{key}_norm"] = None if math.isnan(v) else v

    return corridors


def compute_composite_scores(
    corridors: list[dict],
    config: Optional[ScoringConfig] = None,
) -> list[dict]:
    """Compute the final CVS for each corridor.

    If SCI or CRS normalised values are missing, CVS is set to None rather
    than a misleading zero. HIS-only proxies are exposed separately so the
    UI can show "hazard-only" corridors without pretending they're ranked
    on structural grounds.
    """
    if config is None:
        config = ScoringConfig()

    for c in corridors:
        sci_norm = c.get("sci_norm")
        crs_norm = c.get("crs_norm")
        his_norm = c.get("his_norm")
        pas_norm = c.get("pas_norm") or 0.0
        sccs_norm = c.get("sccs_norm") or 0.0

        # Hazard-only proxy: a number that is meaningful even without
        # structural data. Frontend can use this for the hazard tab when CVS
        # is None.
        c["cvs_hazard_only"] = his_norm if his_norm is not None else None

        # Full CVS requires every structural component we rely on.
        missing_structural = sci_norm is None or crs_norm is None or his_norm is None
        if missing_structural:
            c["cvs"] = None
            c["cvs_missing_inputs"] = [
                k for k, v in (("sci_norm", sci_norm),
                               ("crs_norm", crs_norm),
                               ("his_norm", his_norm))
                if v is None
            ]
            continue

        if config.composition_method == CompositionMethod.HYBRID:
            cvs = ScoringEngine.hybrid(
                sci_norm, crs_norm, his_norm, pas_norm, sccs_norm,
                config.w_hazard, config.w_price, config.w_supply_chain,
            )
        elif config.composition_method == CompositionMethod.WEIGHTED_LINEAR:
            vals = [sci_norm, crs_norm, his_norm, pas_norm, sccs_norm]
            wts = ScoringEngine.equal_weights(len(vals))
            cvs = ScoringEngine.weighted_linear(vals, wts)
        elif config.composition_method == CompositionMethod.GEOMETRIC_MEAN:
            vals = [sci_norm, crs_norm, his_norm, pas_norm, sccs_norm]
            wts = ScoringEngine.equal_weights(len(vals))
            cvs = ScoringEngine.geometric_mean(vals, wts)
        else:
            cvs = 0.0

        c["cvs"] = cvs
        c["cvs_missing_inputs"] = []

    return corridors


def run_scoring_pipeline(
    corridors: list[dict],
    config: Optional[ScoringConfig] = None,
) -> list[dict]:
    """Full scoring pipeline: normalise then compose.

    Returns corridors sorted by CVS descending; corridors with CVS=None fall
    to the bottom (they lack structural inputs and can't be ranked with it).
    """
    corridors = normalise_corridor_scores(corridors, config)
    corridors = compute_composite_scores(corridors, config)
    corridors.sort(
        key=lambda c: c.get("cvs") if c.get("cvs") is not None else -1.0,
        reverse=True,
    )
    return corridors
