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
    # `pas` and `sccs` are populated by Slice E2; until then they remain absent
    # on every corridor and the normaliser turns them into all-NaN columns,
    # which compute_composite_scores treats as "term not active".
    keys_to_normalise = ["sci", "his", "crs", "pas", "sccs"]

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

    CVS requires a structural base (SCI) and a hazard signal (HIS). Consumption
    demand (CRS) is used when present but is OPTIONAL: the hybrid base would
    otherwise be SCI*CRS and collapse to zero everywhere FAOSTAT FBS data is
    missing. When CRS is absent we fall back to an SCI-only base amplified by
    HIS, and tag `cvs_mode = "sci_his"` so the UI can distinguish it from the
    full `"sci_crs_his"` score.

    Amplifier masking (Slice E1): only amplifier terms whose normalised value
    is available contribute to BOTH the numerator and the divisor. The Rust
    `score_hybrid` always divides by `1 + w_h + w_p + w_sc`, which caps the
    full-data mode (PAS/SCCS missing) at 0.5 while the sci_his fallback
    reaches 1.0 — inverting the rank order. We do the math in Python instead
    so the divisor stays consistent with which terms are actually wired.

    Corridors lacking SCI or HIS still get `cvs = None` (no fabricated rank);
    `cvs_hazard_only` exposes the HIS percentile for the hazard-only view.
    """
    if config is None:
        config = ScoringConfig()

    for c in corridors:
        sci_norm = c.get("sci_norm")
        crs_norm = c.get("crs_norm")
        his_norm = c.get("his_norm")
        pas_norm = c.get("pas_norm")
        sccs_norm = c.get("sccs_norm")

        c["cvs_hazard_only"] = his_norm if his_norm is not None else None

        # Core requirement (relaxed): structural reliance + hazard signal.
        missing_core = sci_norm is None or his_norm is None
        if missing_core:
            c["cvs"] = None
            c["cvs_mode"] = None
            c["cvs_amplifier_terms"] = []
            c["cvs_missing_inputs"] = [
                k for k, v in (("sci_norm", sci_norm), ("his_norm", his_norm))
                if v is None
            ]
            continue

        has_crs = crs_norm is not None

        # Active amplifier terms (Slice E1): each contributes (w·v) to the
        # numerator and w to the divisor. None terms drop out of both, keeping
        # full-data and partial-data corridors on the same [0,1] scale.
        amplifier_candidates = [
            ("his", his_norm, config.w_hazard),
            ("pas", pas_norm, config.w_price),
            ("sccs", sccs_norm, config.w_supply_chain),
        ]
        active_terms = [
            (name, val, w) for name, val, w in amplifier_candidates if val is not None
        ]

        if config.composition_method == CompositionMethod.HYBRID:
            # CRS fallback: use 0.5 (median percentile rank) when consumption
            # data is missing. Treating missing data as 1.0 would let sci_his
            # lanes outrank sci_crs_his lanes with mid-range CRS — a perverse
            # incentive where data-poor lanes win. 0.5 says "no information",
            # neither favouring nor penalising the fallback mode.
            crs_factor = crs_norm if has_crs else 0.5
            base = sci_norm * crs_factor
            amplifier = 1.0 + sum(w * v for _, v, w in active_terms)
            max_amp = 1.0 + sum(w for _, _, w in active_terms)
            cvs = (base * amplifier / max_amp) if max_amp > 0 else 0.0
            c["cvs_amplifier_terms"] = [name for name, _, _ in active_terms]
        elif config.composition_method == CompositionMethod.WEIGHTED_LINEAR:
            vals = [sci_norm, his_norm] + ([crs_norm] if has_crs else [])
            cvs = ScoringEngine.weighted_linear(vals, ScoringEngine.equal_weights(len(vals)))
            c["cvs_amplifier_terms"] = ["his"]
        elif config.composition_method == CompositionMethod.GEOMETRIC_MEAN:
            vals = [sci_norm, his_norm] + ([crs_norm] if has_crs else [])
            cvs = ScoringEngine.geometric_mean(vals, ScoringEngine.equal_weights(len(vals)))
            c["cvs_amplifier_terms"] = ["his"]
        else:
            cvs = 0.0
            c["cvs_amplifier_terms"] = []

        c["cvs"] = cvs
        c["cvs_mode"] = "sci_crs_his" if has_crs else "sci_his"
        c["cvs_missing_inputs"] = [] if has_crs else ["crs_norm"]

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
