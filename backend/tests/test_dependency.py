"""Section 2 dependency: worked example, batch pipeline, provenance/flags."""

import math

import numpy as np

from defensefood.core import DependencyEngine
from defensefood.pipeline.dependency_pipeline import (
    compute_corridor_dependency,
    run_dependency_pipeline,
)
from tests.fixtures import (
    WORKED_DEST,
    WORKED_HS,
    WORKED_ORIGIN,
    WORKED_PERIOD,
    synthetic_faostat_store,
    worked_example_trade_df,
)


def test_compute_all_matches_pdf_worked_example():
    res = DependencyEngine.compute_all(
        production_kg=500.0,
        total_imports_kg=12000.0,
        total_exports_kg=1500.0,
        bilateral_import_kg=8000.0,
        all_origin_imports=np.array([8000.0, 2000.0, 1500.0, 500.0]),
    )
    assert math.isclose(res["ds_prime"], 11000.0, rel_tol=1e-9)
    assert math.isclose(res["idr"], 1.0909090909, rel_tol=1e-6)
    assert math.isclose(res["ocs"], 0.6666666667, rel_tol=1e-6)
    assert math.isclose(res["hhi"], 0.4895833333, rel_tol=1e-6)
    assert math.isclose(res["sci"], 1.0833333333, rel_tol=1e-6)
    assert math.isclose(res["sci_norm"], 0.5416666667, rel_tol=1e-6)


def test_delta_stocks_feeds_supply_balance():
    base = DependencyEngine.compute_all(500.0, 12000.0, 1500.0, 8000.0)
    with_stock = DependencyEngine.compute_all(
        500.0, 12000.0, 1500.0, 8000.0, delta_stocks_kg=1000.0
    )
    assert math.isclose(with_stock["ds_prime"] - base["ds_prime"], 1000.0, rel_tol=1e-9)


def test_corridor_dependency_from_trade_df_with_production():
    df = worked_example_trade_df()
    res = compute_corridor_dependency(
        df, WORKED_HS, WORKED_DEST, WORKED_ORIGIN, WORKED_PERIOD,
        production_kg=500.0, provenance="faostat",
    )
    assert "error" not in res
    assert math.isclose(res["ds_prime"], 11000.0, rel_tol=1e-9)
    assert math.isclose(res["ocs"], 0.6666666667, rel_tol=1e-6)
    assert res["provenance"] == "faostat"
    assert res["idr_gt_1"] is True  # 12000 / 11000 > 1
    assert math.isclose(res["bilateral_import_kg"], 8000.0, rel_tol=1e-9)


def test_batch_pipeline_uses_faostat_and_precomputed_hhi():
    df = worked_example_trade_df()
    store = synthetic_faostat_store()
    keys = [(WORKED_HS, WORKED_DEST, WORKED_ORIGIN)]
    out = run_dependency_pipeline(df, keys, store, WORKED_PERIOD)
    assert keys[0] in out
    r = out[keys[0]]
    assert r["provenance"] == "faostat"
    assert math.isclose(r["hhi"], 0.4895833333, rel_tol=1e-6)
    assert math.isclose(r["sci"], 1.0833333333, rel_tol=1e-5)


def test_batch_pipeline_trade_only_fallback():
    df = worked_example_trade_df()
    keys = [(WORKED_HS, WORKED_DEST, WORKED_ORIGIN)]
    out = run_dependency_pipeline(df, keys, faostat=None, period=WORKED_PERIOD)
    r = out[keys[0]]
    assert r["provenance"] == "trade_only"
    # trade-only DS' = M - X = 12000 - 1500 = 10500
    assert math.isclose(r["ds_prime"], 10500.0, rel_tol=1e-9)


def test_batch_pipeline_skips_corridors_without_trade():
    df = worked_example_trade_df()
    keys = [("999999", 56, 251)]  # HS not in trade
    out = run_dependency_pipeline(df, keys, faostat=None, period=WORKED_PERIOD)
    assert keys[0] not in out
