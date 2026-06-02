"""Tests for corridor data-quality annotations."""

from defensefood.pipeline.data_quality import (
    REASON_DS_PRIME_ERROR,
    REASON_NO_TRADE_FOOTPRINT,
    REASON_OK,
    REASON_ZERO_DESTINATION_IMPORTS,
    annotate_corridor_data_quality,
)


def test_full_lane_ok():
    m = {"sci": 0.5, "sci_norm": 0.4, "cvs": 0.3, "his": 0.2}
    annotate_corridor_data_quality(m)
    assert m["data_quality"] == "full"
    assert m["sci_unavailable_reason"] is None


def test_zero_imports_hazard_only():
    m = {
        "sci": None,
        "total_imports_kg": 0.0,
        "bilateral_import_kg": 0.0,
        "production_kg": 1e9,
        "provenance": "faostat",
        "his": 0.75,
        "cvs_hazard_only": 0.99,
    }
    annotate_corridor_data_quality(m)
    assert m["sci_unavailable_reason"] == REASON_ZERO_DESTINATION_IMPORTS
    assert m["data_quality"] == "hazard_only"
    assert "No destination imports" in (m["sci_unavailable_label"] or "")


def test_no_trade_footprint():
    m = {"his": 0.1, "notification_count": 1}
    annotate_corridor_data_quality(m)
    assert m["sci_unavailable_reason"] == REASON_NO_TRADE_FOOTPRINT
    assert m["data_quality"] == "hazard_only"


def test_ds_prime_error():
    m = {
        "dependency_error": "DS' <= 0, data quality issue (flag and exclude)",
        "his": 0.5,
    }
    annotate_corridor_data_quality(m)
    assert m["sci_unavailable_reason"] == REASON_DS_PRIME_ERROR
