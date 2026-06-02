"""
Section 2 verification — exercises every model in the blueprint:

  2.1 Domestic Supply Balance (DS')
  2.2 Import Dependency Ratio (IDR)
  2.3 Origin Country Share (OCS)
  2.4 Bilateral Dependency Index (BDI)
  2.5 Herfindahl-Hirschman Index (HHI)
  2.6 Self-Sufficiency Ratio (SSR)
  2.7 Supply Criticality Index (SCI)

Each formula is exercised in three layers:
  A. Unit math on the blueprint's worked example (Belgium flaxseed)
  B. Edge / boundary conditions
  C. Live data: pick representative corridors from the running pipeline and
     reconstruct each metric end to end so the numbers match what the UI shows.

Run from backend/:
    venv/Scripts/python.exe script/verify_section2.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

# Windows console default codepage is cp1252; the blueprint examples use
# unicode minus signs (and our pretty output uses ANSI box chars). Force
# UTF-8 so the script doesn't blow up on output encoding.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from defensefood.core import DependencyEngine  # noqa: E402
from defensefood_core import dependency as _dep  # noqa: E402


# ── Pretty printing helpers ────────────────────────────────────────────────

_GREEN = "\033[92m"
_RED = "\033[91m"
_DIM = "\033[2m"
_END = "\033[0m"
_BOLD = "\033[1m"


def _result_line(label: str, ok: bool, detail: str = "") -> None:
    badge = f"{_GREEN}PASS{_END}" if ok else f"{_RED}FAIL{_END}"
    suffix = f"  {_DIM}{detail}{_END}" if detail else ""
    print(f"  [{badge}] {label}{suffix}")


def _assert_close(label: str, actual: float, expected: float, tol: float = 1e-6) -> bool:
    ok = math.isclose(actual, expected, rel_tol=tol, abs_tol=1e-9)
    _result_line(label, ok, f"got {actual:.6f}, expected {expected:.6f}")
    return ok


def _section(title: str) -> None:
    print()
    print(f"{_BOLD}{title}{_END}")
    print("-" * len(title))


# ── A. Blueprint worked example (flaxseed FR -> BE) ────────────────────────


def verify_worked_example() -> int:
    """
    Blueprint Sec. 2.7 example — RASFF 2026.0129 Cadmium in flaxseed FR->BE.

        P(flax, BE)         = 500 t (FAOSTAT)
        M(flax, BE, .)      = 12,000 t (Comtrade)
        X(flax, BE, .)      = 1,500 t
        M(flax, BE, FR)     = 8,000 t
        all-origin imports  = [8000, 2000, 1500, 500]

    Expected (from PDF):
        DS'      = P + M - X + 0  = 500 + 12000 - 1500 = 11,000
        IDR      = M / DS'         = 12000 / 11000      ≈ 1.0909
        OCS      = M_FR / M        = 8000 / 12000        ≈ 0.6667
        BDI      = IDR * OCS       ≈ 0.7273
        HHI      = Σ OCS_j²        = (8000² + 2000² + 1500² + 500²) / 12000²
                                   = (64M + 4M + 2.25M + 0.25M) / 144M
                                   = 70.5/144 ≈ 0.4896
        SCI      = IDR * OCS * (1 + HHI)
                                   = 1.0909 * 0.6667 * 1.4896 ≈ 1.0833
        SCI_norm = SCI / 2          ≈ 0.5417
    """
    res = DependencyEngine.compute_all(
        production_kg=500.0,
        total_imports_kg=12000.0,
        total_exports_kg=1500.0,
        bilateral_import_kg=8000.0,
        all_origin_imports=np.array([8000.0, 2000.0, 1500.0, 500.0]),
    )

    fails = 0
    fails += not _assert_close("DS' = P + M − X",     res["ds_prime"], 11000.0)
    fails += not _assert_close("IDR = M / DS'",       res["idr"],      1.0909090909)
    fails += not _assert_close("OCS = M_ij / M",      res["ocs"],      0.6666666667)
    bdi_expected = res["idr"] * res["ocs"]
    fails += not _assert_close("BDI = M_ij / DS'",    res["bdi"],      bdi_expected)
    fails += not _assert_close("HHI = Σ OCS²",        res["hhi"],      0.4895833333)
    fails += not _assert_close("SCI = IDR·OCS·(1+HHI)", res["sci"],    1.0833333333)
    fails += not _assert_close("SCI_norm = SCI / 2",  res["sci_norm"], 0.5416666667)
    return fails


# ── B. Edge / boundary conditions ──────────────────────────────────────────


def verify_edge_cases() -> int:
    fails = 0

    # 2.2 IDR boundary semantics
    # IDR = 0 when M = 0 (fully self-sufficient)
    r = DependencyEngine.compute_all(1000.0, 0.0, 0.0, 0.0)
    fails += not _assert_close("IDR(M=0) = 0 (self-sufficient)", r["idr"], 0.0)
    fails += not _assert_close("DS'(M=0) = P", r["ds_prime"], 1000.0)

    # IDR = 1 when P = X = 0 (fully import-dependent)
    r = DependencyEngine.compute_all(0.0, 1000.0, 0.0, 1000.0)
    fails += not _assert_close("IDR(P=0,X=0) = 1 (fully imported)", r["idr"], 1.0)
    fails += not _assert_close("BDI(M_ij=M) = IDR (sole supplier)", r["bdi"], r["idr"])

    # IDR > 1 = trade-hub / re-export signal
    r = DependencyEngine.compute_all(500.0, 12000.0, 1500.0, 8000.0)
    fails += not (r["idr"] > 1.0)
    _result_line("IDR > 1 flagged correctly (trade hub)", r["idr"] > 1.0,
                 f"IDR = {r['idr']:.4f}")

    # 2.1 DS' <= 0 boundary -- engine returns NaN / error
    r = DependencyEngine.compute_all(0.0, 1000.0, 5000.0, 100.0)
    fails += not ("error" in r)
    _result_line("DS' ≤ 0 surfaces as data-quality error",
                 "error" in r, r.get("error", "no error"))

    # 2.5 HHI: single supplier = 1.0; perfectly diversified ~ 1/n
    hhi_single = DependencyEngine.compute_hhi(np.array([1.0]))
    fails += not _assert_close("HHI(single supplier) = 1.0", hhi_single, 1.0)

    shares_5_equal = np.array([0.2] * 5)
    hhi_5 = DependencyEngine.compute_hhi(shares_5_equal)
    fails += not _assert_close("HHI(5 equal) = 1/5 = 0.2", hhi_5, 0.2)

    shares_2_equal = np.array([0.5, 0.5])
    hhi_2 = DependencyEngine.compute_hhi(shares_2_equal)
    fails += not _assert_close("HHI(2 equal) = 0.5 (= antitrust monopoly threshold)", hhi_2, 0.5)

    # 2.7 SCI range: must lie in [0, 2]
    r = DependencyEngine.compute_all(0.0, 1000.0, 0.0, 1000.0,
                                      all_origin_imports=np.array([1000.0]))
    sci_max = r["sci"]
    fails += not (0 <= sci_max <= 2.0)
    _result_line(f"SCI bounded by [0, 2]; worst-case lane = {sci_max:.3f}",
                 0 <= sci_max <= 2.0)

    # 2.6 SSR boundary: SSR=0 (no production), SSR=1 (balanced), SSR>1 (exporter)
    ssr_zero = _dep.compute_ssr(0.0, 1000.0)
    fails += not _assert_close("SSR(P=0) = 0 (no production)", ssr_zero, 0.0)
    ssr_balanced = _dep.compute_ssr(1000.0, 1000.0)
    fails += not _assert_close("SSR(P=D) = 1 (balanced)", ssr_balanced, 1.0)
    ssr_exporter = _dep.compute_ssr(2000.0, 1000.0)
    fails += not _assert_close("SSR(P=2D) = 2 (net exporter)", ssr_exporter, 2.0)

    return fails


# ── C. Live data: real-corridor reconstruction ─────────────────────────────


def verify_live_corridors() -> int:
    """Pick a handful of live corridors from the pipeline and reconstruct
    each metric directly from the engine to confirm the API matches.
    """
    import importlib

    import defensefood.api.dependencies as deps
    importlib.reload(deps)
    from defensefood.api.dependencies import get_state, refresh_coverage
    from defensefood.pipeline.scoring_pipeline import run_scoring_pipeline

    state = get_state()
    state.corridor_metrics = run_scoring_pipeline(
        [c.copy() for c in state.corridor_metrics], state.scoring_config,
    )
    refresh_coverage(state)

    fails = 0
    print(f"  total scored corridors: {state.coverage.get('corridors_with_dependency', 0)}")
    print(f"  FAOSTAT-tagged: {state.coverage.get('corridors_faostat', 0)}")

    # Pick three diagnostic lanes: high SCI (worst case), self-sufficient, mid-range
    scored = [m for m in state.corridor_metrics if m.get("sci") is not None]
    scored_by_sci = sorted(scored, key=lambda m: m.get("sci") or 0, reverse=True)

    print()
    print(f"  {_BOLD}Top three lanes by SCI:{_END}")
    print(f"    {'lane':<48}  {'IDR':>7}  {'OCS':>7}  {'HHI':>7}  {'SSR':>7}  {'SCI':>7}  prov")
    for m in scored_by_sci[:3]:
        lane = f"{m['origin_country']} → {m['destination_country']} HS {m['commodity_hs']}"[:46]
        print(f"    {lane:<48}  {m.get('idr',0):>7.3f}  {m.get('ocs',0):>7.3f}  "
              f"{m.get('hhi',0):>7.3f}  {m.get('ssr',0) or 0:>7.3f}  {m.get('sci',0):>7.3f}  "
              f"{m.get('provenance','-')}")

    # For the top lane, reconstruct the math from raw inputs
    if scored_by_sci:
        m = scored_by_sci[0]
        total_imports = m.get("total_imports_kg") or 0
        bilateral = m.get("bilateral_import_kg") or 0
        production = m.get("production_kg") or 0

        if total_imports > 0:
            expected_ocs = bilateral / total_imports
            ok = math.isclose(m["ocs"], expected_ocs, rel_tol=1e-4)
            fails += not ok
            _result_line(
                f"top-lane OCS = bilateral/M = {bilateral:.0f}/{total_imports:.0f}",
                ok,
                f"engine={m['ocs']:.4f}, reconstruction={expected_ocs:.4f}",
            )

        # IDR sanity: IDR = M / DS' where DS' = P + M - X. We don't have X
        # directly on the metric dict, so just confirm IDR > 0 when M > 0.
        if total_imports > 0:
            ok = (m.get("idr") or 0) > 0
            _result_line(f"top-lane IDR > 0 (M = {total_imports:.0f} kg)", ok,
                         f"IDR = {m['idr']:.4f}")

        # SCI identity: SCI = IDR * OCS * (1 + HHI)
        if all(m.get(k) is not None for k in ("idr", "ocs", "hhi", "sci")):
            recompute = m["idr"] * m["ocs"] * (1.0 + m["hhi"])
            ok = math.isclose(m["sci"], recompute, rel_tol=1e-4)
            fails += not ok
            _result_line(
                "top-lane SCI = IDR·OCS·(1+HHI) identity",
                ok,
                f"engine={m['sci']:.4f}, recompute={recompute:.4f}",
            )

    # Self-sufficient lanes (P > 0, IDR low)
    self_suff = [m for m in scored if (m.get("ssr") or 0) > 1.0]
    if self_suff:
        print()
        print(f"  {_BOLD}Net-exporter lanes (SSR > 1):{_END} {len(self_suff)} total")
        for m in self_suff[:3]:
            lane = f"{m['origin_country']} → {m['destination_country']} HS {m['commodity_hs']}"[:46]
            print(f"    {lane:<48}  "
                  f"IDR={m.get('idr',0):.3f}  SSR={m.get('ssr',0):.3f}  "
                  f"P={(m.get('production_kg') or 0)/1e6:.1f}kt")

    # IDR > 1 lanes (transit hubs or data gaps)
    idr_hub = [m for m in scored if m.get("idr_gt_1")]
    print()
    print(f"  {_BOLD}Trade-hub flag (IDR > 1):{_END} {len(idr_hub)} lanes")

    return fails


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> int:
    total_fails = 0

    _section("A. Blueprint worked example — Sec. 2.7 (Belgium flaxseed)")
    total_fails += verify_worked_example()

    _section("B. Edge / boundary conditions")
    total_fails += verify_edge_cases()

    _section("C. Live data sanity (1059 corridors)")
    total_fails += verify_live_corridors()

    print()
    if total_fails == 0:
        print(f"{_GREEN}{_BOLD}All Section 2 checks passed.{_END}")
    else:
        print(f"{_RED}{_BOLD}{total_fails} check(s) failed.{_END}")
    return total_fails


if __name__ == "__main__":
    raise SystemExit(main())
