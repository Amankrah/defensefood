"""Audit CVS distribution after E1+E2 (Slice E4 prep).

Runs the live scoring pipeline against the cached corridor metrics and prints
P50/P75/P90/P95 of the resulting CVS. These quantiles drive the re-banded
``interpretCvs`` thresholds and the CVS scale array in the methodology
catalogue.

Output is also written to ``backend/script/output/cvs_distribution_postE2.json``
so the scoring test can pin the chosen thresholds against the recorded
distribution.

Usage:
    python -m script.audit_cvs_distribution
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import defensefood.api.dependencies as deps_module
from defensefood.pipeline.scoring_pipeline import run_scoring_pipeline


def quantile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolation quantile on a pre-sorted list."""
    if not sorted_vals:
        return float("nan")
    if q <= 0:
        return sorted_vals[0]
    if q >= 1:
        return sorted_vals[-1]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])


def main() -> None:
    deps_module._state = None
    state = deps_module.get_state()
    scored = run_scoring_pipeline(
        [c.copy() for c in state.corridor_metrics],
        state.scoring_config,
    )
    state.corridor_metrics = scored

    cvs_vals = sorted(c["cvs"] for c in scored if c.get("cvs") is not None)
    if not cvs_vals:
        print("No CVS values present — nothing to audit.")
        return

    summary = {
        "n_scored": len(cvs_vals),
        "n_total": len(scored),
        "min": cvs_vals[0],
        "max": cvs_vals[-1],
        "mean": statistics.fmean(cvs_vals),
        "median": quantile(cvs_vals, 0.50),
        "p75": quantile(cvs_vals, 0.75),
        "p90": quantile(cvs_vals, 0.90),
        "p95": quantile(cvs_vals, 0.95),
    }

    # Amplifier-term distribution (sanity check that E2 wired through).
    from collections import Counter
    amp_terms = Counter(
        tuple(c.get("cvs_amplifier_terms", [])) for c in scored
    )
    summary["amplifier_distribution"] = {
        ",".join(k) or "<none>": v for k, v in amp_terms.most_common()
    }
    summary["mode_distribution"] = dict(
        Counter(c.get("cvs_mode") for c in scored)
    )

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "cvs_distribution_postE2.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str))

    print(f"CVS distribution audit (n={len(cvs_vals)})")
    for k in ("min", "median", "p75", "p90", "p95", "max"):
        print(f"  {k:7s} {summary[k]:.4f}")
    print()
    print(f"Wrote {out_path}")
    print()
    print("Suggested band thresholds (matching the audit quantiles):")
    print(f"  low       0   .. {summary['p75']:.2f}")
    print(f"  watchlist {summary['p75']:.2f} .. {summary['p90']:.2f}")
    print(f"  high      {summary['p90']:.2f} .. {summary['p95']:.2f}")
    print(f"  top       {summary['p95']:.2f} .. 1.00")


if __name__ == "__main__":
    main()
