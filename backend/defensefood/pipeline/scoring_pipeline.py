"""
Scoring Pipeline -- Section 7 computation orchestration.

Normalises sub-scores from all prior sections and composes them into
the final Composite Vulnerability Score (CVS) per corridor.
"""

from typing import Optional

import numpy as np
import pandas as pd

from defensefood.core import ScoringEngine
from defensefood.models.scores import CompositionMethod, NormalisationMethod, ScoringConfig


def normalise_corridor_scores(
    corridors: list[dict],
    config: Optional[ScoringConfig] = None,
) -> list[dict]:
    """Normalise raw sub-scores across all corridors.

    Each corridor dict should have raw values for: sci, his, crs, pas, sccs.
    Returns corridors with added *_norm keys.
    """
    if config is None:
        config = ScoringConfig()

    method = config.normalisation_method.value

    # Extract raw score arrays
    keys_to_normalise = ["sci", "his", "crs"]
    raw_arrays = {}
    for key in keys_to_normalise:
        values = [c.get(key, 0.0) for c in corridors]
        raw_arrays[key] = np.array(values, dtype=float)

    # Normalise each
    norm_arrays = {}
    for key, arr in raw_arrays.items():
        if key == "his" and method != "log_percentile":
            # HIS is highly skewed (exponential distribution of notification counts)
            # Framework recommends log-percentile for HIS
            norm_arrays[key] = ScoringEngine.normalise(arr, "log_percentile")
        else:
            norm_arrays[key] = ScoringEngine.normalise(arr, method)

    # Write back normalised values
    for i, c in enumerate(corridors):
        for key in keys_to_normalise:
            c[f"{key}_norm"] = float(norm_arrays[key][i])

    return corridors


def compute_composite_scores(
    corridors: list[dict],
    config: Optional[ScoringConfig] = None,
) -> list[dict]:
    """Compute the final CVS for each corridor.

    Requires corridors to have *_norm keys (call normalise_corridor_scores first).
    """
    if config is None:
        config = ScoringConfig()

    for c in corridors:
        sci_norm = c.get("sci_norm", 0.0)
        crs_norm = c.get("crs_norm", 0.0)
        his_norm = c.get("his_norm", 0.0)
        pas_norm = c.get("pas_norm", 0.0)
        sccs_norm = c.get("sccs_norm", 0.0)

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

    return corridors


def run_scoring_pipeline(
    corridors: list[dict],
    config: Optional[ScoringConfig] = None,
) -> list[dict]:
    """Full scoring pipeline: normalise then compose.

    Returns corridors sorted by CVS descending.
    """
    corridors = normalise_corridor_scores(corridors, config)
    corridors = compute_composite_scores(corridors, config)
    corridors.sort(key=lambda c: c.get("cvs", 0.0), reverse=True)
    return corridors
