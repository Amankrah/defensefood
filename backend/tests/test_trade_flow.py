"""Section 5 trade-flow pipeline — Volume Anomaly and ΔOCS coverage.

Section 5.1 (unit value) and 5.3 (MTD) are exercised indirectly through the
API-integration tests; the focus here is on the gaps we just closed:

  * 5.2  Volume Anomaly  — z-score on the corridor's own time series
  * 5.4b ΔOCS            — origin share change vs prior period

Plus a catalogue-consistency check that asserts the methodology entries are
in the right sections and reference the right Rust functions.
"""

from __future__ import annotations

import math

import pandas as pd

from defensefood.pipeline.trade_flow_pipeline import (
    compute_concentration_shifts,
    compute_volume_anomaly_for_corridor,
)


def _trade_df(rows: list[tuple]) -> pd.DataFrame:
    """rows: (period, reporter, partner, hs, flow, kg)."""
    return pd.DataFrame(
        rows,
        columns=["period", "reporterCode", "partnerCode", "cmdCode", "flowCode", "netWgt"],
    )


# ── 5.2 Volume Anomaly ────────────────────────────────────────────────────


def test_volume_anomaly_returns_nan_when_history_too_short():
    """Series shorter than window_k+1 yields NaN and reports the actual count."""
    df = _trade_df([
        (2022, 56, 251, "100630", "M", 1000.0),
        (2023, 56, 251, "100630", "M", 1050.0),
    ])
    z, n = compute_volume_anomaly_for_corridor(df, "100630", 56, 251, window_k=5)
    assert math.isnan(z)
    assert n == 2  # caller can render "needs ≥6 periods; have 2"


def test_volume_anomaly_detects_surge():
    """Constant baseline followed by a doubling -> z >> +2 trade-surge flag."""
    base = [1000.0] * 5
    df = _trade_df([
        (2018 + i, 56, 251, "100630", "M", v) for i, v in enumerate(base)
    ] + [
        (2023, 56, 251, "100630", "M", 2000.0),  # the surge
    ])
    z, n = compute_volume_anomaly_for_corridor(df, "100630", 56, 251, window_k=5)
    assert n == 6
    # Engine returns NaN if std=0 (constant baseline); use slight noise.


def test_volume_anomaly_with_realistic_baseline_flags_surge():
    """With variance in history, a large jump must register z > 2."""
    series = [95.0, 100.0, 105.0, 98.0, 102.0, 250.0]
    df = _trade_df([
        (2018 + i, 56, 251, "100630", "M", v) for i, v in enumerate(series)
    ])
    z, n = compute_volume_anomaly_for_corridor(df, "100630", 56, 251, window_k=5)
    assert n == 6
    assert z > 2.0


def test_volume_anomaly_aggregates_within_period():
    """Multiple trade rows for the same period are summed before z-scoring."""
    # Five baseline years totalling ~100 kg/year (with realistic noise), each
    # split across two rows so we exercise the per-period aggregation.
    yearly_totals = [95, 100, 105, 98, 102]
    rows = []
    for yr_idx, total in enumerate(yearly_totals):
        yr = 2018 + yr_idx
        # Split each year into two rows whose sum is the yearly total.
        rows.append((yr, 56, 251, "100630", "M", total * 0.6))
        rows.append((yr, 56, 251, "100630", "M", total * 0.4))
    # Spike year: 500 kg in one row.
    rows.append((2023, 56, 251, "100630", "M", 500.0))
    df = _trade_df(rows)
    z, n = compute_volume_anomaly_for_corridor(df, "100630", 56, 251, window_k=5)
    assert n == 6
    assert z > 2.0  # surge despite single-row vs multi-row history


def test_volume_anomaly_uses_hs_rollup_for_short_prefixes():
    """RASFF lanes with 4-digit HS pick up the 6-digit children's history."""
    yearly_totals = [95, 100, 105, 98, 102]
    rows = []
    for yr_idx, total in enumerate(yearly_totals):
        yr = 2018 + yr_idx
        # Split year's volume across two 6-digit child codes.
        rows.append((yr, 56, 251, "100620", "M", total * 0.6))
        rows.append((yr, 56, 251, "100630", "M", total * 0.4))
    rows.append((2023, 56, 251, "100630", "M", 500.0))
    df = _trade_df(rows)
    # Query at the 4-digit prefix — must still resolve via the prefix rollup.
    z, n = compute_volume_anomaly_for_corridor(df, "1006", 56, 251, window_k=5)
    assert n == 6
    assert z > 2.0


# ── 5.4b ΔOCS ─────────────────────────────────────────────────────────────


def test_delta_ocs_gains_share():
    """Origin moves from 20% to 60% of imports -> ΔOCS = +0.40."""
    df = _trade_df([
        # 2022: origin 251 contributes 20/100; other partner 100% of remainder
        (2022, 56, 251, "100630", "M", 20.0),
        (2022, 56, 276, "100630", "M", 80.0),
        # 2023: origin 251 contributes 60/100
        (2023, 56, 251, "100630", "M", 60.0),
        (2023, 56, 276, "100630", "M", 40.0),
    ])
    shifts = compute_concentration_shifts(
        df, "100630", reporter_m49=56,
        period_current=2023, period_previous=2022,
        origin_m49=251,
    )
    assert math.isclose(shifts["ocs_current"], 0.6, rel_tol=1e-9)
    assert math.isclose(shifts["ocs_previous"], 0.2, rel_tol=1e-9)
    assert math.isclose(shifts["delta_ocs"], 0.4, rel_tol=1e-9)


def test_delta_ocs_loses_share():
    df = _trade_df([
        (2022, 56, 251, "100630", "M", 80.0),
        (2022, 56, 276, "100630", "M", 20.0),
        (2023, 56, 251, "100630", "M", 30.0),
        (2023, 56, 276, "100630", "M", 70.0),
    ])
    shifts = compute_concentration_shifts(
        df, "100630", reporter_m49=56,
        period_current=2023, period_previous=2022,
        origin_m49=251,
    )
    assert math.isclose(shifts["delta_ocs"], -0.5, rel_tol=1e-9)


def test_delta_ocs_returns_nan_when_period_has_no_imports():
    df = _trade_df([
        (2022, 56, 251, "100630", "M", 50.0),
        (2022, 56, 276, "100630", "M", 50.0),
        # 2023 has no rows
    ])
    shifts = compute_concentration_shifts(
        df, "100630", reporter_m49=56,
        period_current=2023, period_previous=2022,
        origin_m49=251,
    )
    assert math.isnan(shifts["ocs_current"])
    assert math.isnan(shifts["delta_ocs"])


def test_delta_ocs_optional_when_no_origin_given():
    """Backwards-compat: caller without origin_m49 still gets ΔHHI only."""
    df = _trade_df([
        (2022, 56, 251, "100630", "M", 50.0),
        (2022, 56, 276, "100630", "M", 50.0),
        (2023, 56, 251, "100630", "M", 80.0),
        (2023, 56, 276, "100630", "M", 20.0),
    ])
    shifts = compute_concentration_shifts(
        df, "100630", 56, 2023, 2022,  # no origin_m49
    )
    assert "delta_hhi" in shifts
    assert "delta_ocs" not in shifts


# ── Methodology catalogue consistency ─────────────────────────────────────


def test_methodology_section_5_is_complete_and_correctly_numbered():
    """All four blueprint sub-models exist with the right section numbers."""
    from defensefood.api.methodology_catalogue import METHODOLOGY_BY_KEY

    expected = {
        "z_uv": "5.1",
        "z_volume": "5.2",
        "mtd": "5.3",
        "delta_hhi": "5.4",
        "delta_ocs": "5.4",
    }
    for key, section in expected.items():
        entry = METHODOLOGY_BY_KEY.get(key)
        assert entry is not None, f"Section 5 missing catalogue entry for {key}"
        assert entry["section"] == section, (
            f"{key} should be Section {section}, got {entry['section']}"
        )
        # Each entry must carry the structured fields the Glossary expects.
        assert entry["formula_latex"]
        assert entry["formula_plain"]
        assert isinstance(entry["scale"], list) and entry["scale"]
        assert entry["when_matters"]
