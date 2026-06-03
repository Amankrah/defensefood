"""Section 6 network pipeline — Slice B correctness gates.

These tests pin the behaviour we just fixed:

  * Missing BDI no longer pollutes ACEP/ORPS with a severity proxy.
  * Real CRS from the Section 3 lookup powers ACEP; no silent 1.0 fallback.
  * ORPS rows surface ``pcc_real_count`` + ``pcc_proxy_count`` per HS so the
    UI can flag stacked-1.0 results.

Subsequent slices (A: role-aware aggregation, C: P̂(hazard|trade)) will add
their own tests alongside.
"""

from __future__ import annotations

import math

import pandas as pd

from defensefood.pipeline.network_pipeline import (
    build_exposure_network,
    count_missing_bdi_edges,
    estimate_avg_shipment_size_by_hs_chapter,
    lookup_avg_shipment_size,
)


def _corridor(**overrides):
    """Minimal corridor metric dict matching what the API state holds.

    Defaults ``market_presence="confirmed"`` so the Slice-A role filter
    on ACEP/ORPS doesn't silently zero these test corridors out — Slice A
    has its own tests that exercise the role filter explicitly.
    """
    base = {
        "commodity_hs": "100630",
        "destination_m49": 56,   # Belgium
        "origin_m49": 250,       # France
        "bdi": 0.4,
        "his": 0.5,
        "severity_total": 9.99,  # would pollute ACEP under the old behaviour
        "bilateral_import_kg": 1000.0,
        "destination_country": "Belgium",
        "origin_country": "France",
        "market_presence": "confirmed",
    }
    base.update(overrides)
    return base


# ── B1: severity proxy removed ────────────────────────────────────────────


def test_missing_bdi_contributes_zero_not_severity():
    """When BDI is missing, ACEP should add 0 for that edge (not severity_total)."""
    # Two corridors: one with real BDI, one without.
    corridors = [
        _corridor(bdi=0.4, his=0.5, severity_total=9.99, commodity_hs="100630"),
        _corridor(bdi=None, his=0.5, severity_total=9.99, commodity_hs="100640"),
    ]
    net = build_exposure_network(corridors)

    # Use CRS=1 for both HS codes so the only variable is dep_weight.
    crs = {"100630": 1.0, "100640": 1.0}
    acep = net.compute_acep(56, crs)

    # Only the BDI=0.4 corridor should contribute: 0.4 * 0.5 * 1.0 = 0.2.
    # If severity_total were still subbed in, ACEP would be 0.2 + 9.99*0.5*1.0 ≈ 5.195.
    assert math.isclose(acep, 0.2, rel_tol=1e-9)


def test_count_missing_bdi_edges_destination_scope():
    corridors = [
        _corridor(bdi=0.4, destination_m49=56),
        _corridor(bdi=None, destination_m49=56, commodity_hs="100640"),
        _corridor(bdi=None, destination_m49=276, commodity_hs="100650"),
    ]
    assert count_missing_bdi_edges(corridors, destination_m49=56) == 1
    assert count_missing_bdi_edges(corridors, destination_m49=276) == 1
    assert count_missing_bdi_edges(corridors) == 2


def test_count_missing_bdi_edges_origin_scope():
    corridors = [
        _corridor(bdi=None, origin_m49=250, commodity_hs="A"),
        _corridor(bdi=0.3, origin_m49=250, commodity_hs="B"),
        _corridor(bdi=None, origin_m49=276, commodity_hs="C"),
    ]
    assert count_missing_bdi_edges(corridors, origin_m49=250) == 1
    assert count_missing_bdi_edges(corridors, origin_m49=276) == 1


# ── B2: real CRS in ACEP ───────────────────────────────────────────────────


def test_acep_uses_real_crs_per_commodity():
    """ACEP must respect different CRS values per commodity, not 1.0."""
    corridors = [
        _corridor(commodity_hs="100630", bdi=0.5, his=0.4),  # wheat
        _corridor(commodity_hs="100640", bdi=0.3, his=0.2),  # rice
    ]
    net = build_exposure_network(corridors)
    crs = {"100630": 0.8, "100640": 0.2}  # wheat is highly ranked, rice not
    acep = net.compute_acep(56, crs)
    # 0.5*0.4*0.8 + 0.3*0.2*0.2 = 0.16 + 0.012 = 0.172
    assert math.isclose(acep, 0.172, rel_tol=1e-9)


def test_acep_missing_crs_drops_to_zero():
    """An HS code without CRS should contribute 0 (no silent 1.0 inflation)."""
    corridors = [_corridor(commodity_hs="100630", bdi=0.5, his=0.4)]
    net = build_exposure_network(corridors)
    acep = net.compute_acep(56, {})  # empty CRS map
    assert acep == 0.0


# ── B3: ORPS PCC fallback is quantified per row ────────────────────────────


# ── Slice A: role-aware ACEP / ORPS ───────────────────────────────────────


def test_acep_default_filters_to_confirmed_only():
    """Informational and unknown lanes contribute 0 to the default ACEP."""
    corridors = [
        _corridor(commodity_hs="A", bdi=0.5, his=0.4, market_presence="confirmed"),
        _corridor(commodity_hs="B", bdi=0.5, his=0.4, market_presence="informational"),
        _corridor(commodity_hs="C", bdi=0.5, his=0.4, market_presence="unknown"),
    ]
    net = build_exposure_network(corridors)
    crs = {"A": 1.0, "B": 1.0, "C": 1.0}
    # Only the confirmed lane counts: 0.5*0.4*1.0 = 0.2.
    assert math.isclose(net.compute_acep(56, crs), 0.2, rel_tol=1e-9)


def test_acep_by_role_returns_all_buckets():
    corridors = [
        _corridor(commodity_hs="A", bdi=0.5, his=0.4, market_presence="confirmed"),
        _corridor(commodity_hs="B", bdi=0.5, his=0.4, market_presence="detected"),
        _corridor(commodity_hs="C", bdi=0.5, his=0.4, market_presence="informational"),
    ]
    net = build_exposure_network(corridors)
    crs = {"A": 1.0, "B": 1.0, "C": 1.0}
    by_role = net.compute_acep_by_role(56, crs)
    assert math.isclose(by_role["confirmed"], 0.2, rel_tol=1e-9)
    assert math.isclose(by_role["detected"], 0.2, rel_tol=1e-9)
    assert math.isclose(by_role["informational"], 0.2, rel_tol=1e-9)
    assert by_role["unknown"] == 0.0


def test_orps_default_filters_to_confirmed_only():
    corridors = [
        _corridor(origin_m49=250, destination_m49=56, commodity_hs="X",
                  bdi=0.6, his=0.5, market_presence="confirmed"),
        _corridor(origin_m49=250, destination_m49=276, commodity_hs="X",
                  bdi=0.6, his=0.5, market_presence="informational"),
    ]
    net = build_exposure_network(corridors)
    pcc = {56: 10.0, 276: 10.0}
    # Only the confirmed destination counts: 0.6*0.5*10 = 3.0
    assert math.isclose(net.compute_orps(250, "X", pcc), 3.0, rel_tol=1e-9)


def test_orps_by_role_splits_buckets():
    corridors = [
        _corridor(origin_m49=250, destination_m49=56, commodity_hs="X",
                  bdi=0.6, his=0.5, market_presence="confirmed"),
        _corridor(origin_m49=250, destination_m49=276, commodity_hs="X",
                  bdi=0.6, his=0.5, market_presence="detected"),
    ]
    net = build_exposure_network(corridors)
    pcc = {56: 10.0, 276: 10.0}
    by_role = net.compute_orps_by_role(250, "X", pcc)
    assert math.isclose(by_role["confirmed"], 3.0, rel_tol=1e-9)
    assert math.isclose(by_role["detected"], 3.0, rel_tol=1e-9)
    assert by_role["informational"] == 0.0


def test_acep_endpoint_returns_role_split():
    """Live state — ACEP endpoint surfaces acep + acep_by_role keys."""
    import defensefood.api.dependencies as deps_module
    from defensefood.api.routers.countries import get_country_acep

    deps_module._state = None
    state = deps_module.get_state()
    # Pick a destination that actually has inbound corridors.
    from collections import Counter
    by_dest = Counter(c.get("destination_m49") for c in state.corridor_metrics)
    dest = by_dest.most_common(1)[0][0]
    payload = get_country_acep(dest, state)
    assert "acep_by_role" in payload
    for role in ("confirmed", "detected", "informational", "unknown"):
        assert role in payload["acep_by_role"]
    # The top-level acep is the confirmed-only number.
    assert math.isclose(payload["acep"], payload["acep_by_role"]["confirmed"], rel_tol=1e-9)


def test_orps_row_carries_pcc_split_counts():
    """The endpoint returns pcc_real_count and pcc_proxy_count per HS row."""
    # Smoke check against the live state — this exercises the wiring path
    # without coupling to specific HS codes or destinations.
    import defensefood.api.dependencies as deps_module
    from defensefood.api.routers.countries import get_orps_by_commodity

    deps_module._state = None  # force re-init so Slice B changes are picked up
    state = deps_module.get_state()
    # Pick the busiest origin in the live dataset (avoids fixturing).
    from collections import Counter
    by_origin = Counter(c.get("origin_m49") for c in state.corridor_metrics)
    most_common_origin = by_origin.most_common(1)[0][0]

    payload = get_orps_by_commodity(most_common_origin, state)
    rows = payload["commodities"]
    assert rows, "expected at least one ORPS row for the busiest origin"
    for r in rows:
        assert "pcc_real_count" in r
        assert "pcc_proxy_count" in r
        assert r["pcc_real_count"] >= 0
        assert r["pcc_proxy_count"] >= 0


# ── Slice C: Eq. 35 average shipment size + endpoint ──────────────────────


def _trade_df_for_mbar(rows):
    """rows: list of (cmdCode, netWgt). Other columns padded with sensible defaults."""
    return pd.DataFrame(
        [
            {
                "cmdCode": str(hs),
                "netWgt": kg,
                "period": 2023,
                "reporterCode": 56,
                "partnerCode": 250,
                "flowCode": "M",
            }
            for hs, kg in rows
        ]
    )


def test_avg_shipment_size_chapter_median_with_enough_rows():
    """A chapter with ≥30 rows gets its own median; sparse chapters fall back."""
    rows = []
    # Chapter 10 (cereals): 40 rows around 25,000 kg → median ≈ 25,000.
    for i in range(40):
        rows.append(("100630", 24_500 + (i % 20) * 50))
    # Chapter 03 (fish): only 5 rows → not enough for own median, must fall back.
    for v in (1_000, 1_100, 1_200, 1_300, 1_400):
        rows.append(("030749", v))
    df = _trade_df_for_mbar(rows)
    lookup = estimate_avg_shipment_size_by_hs_chapter(df, min_rows=30)
    assert "global" in lookup
    assert "10" in lookup
    assert lookup["10"] > 0
    # Sparse chapter excluded (lookup falls back to global on query).
    assert "03" not in lookup


def test_avg_shipment_size_handles_empty_trade_df():
    df = pd.DataFrame(columns=["cmdCode", "netWgt", "period"])
    lookup = estimate_avg_shipment_size_by_hs_chapter(df)
    assert lookup == {"global": 0.0}


def test_lookup_avg_shipment_size_falls_back_to_global():
    lookup = {"10": 25000.0, "global": 8000.0}
    # HS code in chapter 10 → chapter median.
    assert lookup_avg_shipment_size(lookup, "100630") == 25000.0
    # HS code in a chapter not in the lookup → global fallback.
    assert lookup_avg_shipment_size(lookup, "070130") == 8000.0
    # Missing/empty HS → global.
    assert lookup_avg_shipment_size(lookup, "") == 8000.0


def test_hazard_probability_endpoint_eligibility_gate():
    """The endpoint enforces the ≥10-notification gate per blueprint Sec. 6.4."""
    import defensefood.api.dependencies as deps_module
    from defensefood.api.routers.corridors import get_corridor_hazard_probability

    deps_module._state = None
    state = deps_module.get_state()

    # Find one eligible and one ineligible corridor in live state.
    eligible = next(
        (c for c in state.corridor_metrics if (c.get("notification_count") or 0) >= 10),
        None,
    )
    assert eligible is not None, "expected at least one eligible corridor in live state"

    out = get_corridor_hazard_probability(
        eligible["commodity_hs"],
        eligible["destination_m49"],
        eligible["origin_m49"],
        state,
    )
    if (eligible.get("bilateral_import_kg") or 0) > 0:
        assert out["eligible"] is True
        assert out["p_hat"] is not None
        assert out["p_hat"] >= 0
    else:
        assert out["eligible"] is False
        assert "trade footprint" in (out["eligibility_reason"] or "")

    ineligible = next(
        (c for c in state.corridor_metrics if 0 < (c.get("notification_count") or 0) < 10),
        None,
    )
    if ineligible is not None:
        out2 = get_corridor_hazard_probability(
            ineligible["commodity_hs"],
            ineligible["destination_m49"],
            ineligible["origin_m49"],
            state,
        )
        assert out2["eligible"] is False
        assert out2["p_hat"] is None
        assert "10 notifications" in (out2["eligibility_reason"] or "").lower() or \
               "have " in (out2["eligibility_reason"] or "").lower()


def test_methodology_catalogue_has_hazard_probability_entry():
    """Glossary + Methodology tab consume this; entry must exist with bands."""
    from defensefood.api.methodology_catalogue import METHODOLOGY_BY_KEY

    entry = METHODOLOGY_BY_KEY.get("hazard_probability")
    assert entry is not None
    assert entry["section"] == "6.4"
    assert "scale" in entry and len(entry["scale"]) >= 3
    assert "formula_latex" in entry
    assert "dgi" in entry["related"]
