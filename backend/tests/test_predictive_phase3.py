"""
Phase 3 of the predictive epic — agent subsystem integration.

Tests cover:

1. ``predict_lane_next_period`` agent tool — happy path with a fitted
   forecaster on the fixture, graceful fallback when forecaster is None,
   no-history case.
2. ``GET /api/v1/agent/forecast/{hs}/{dest}/{origin}`` endpoint — unwraps
   the tool result, returns 200 in both success and "unavailable" cases
   so the frontend can render either without a try/catch.
3. Anomaly explainer preload picks up the ``model_outlook`` field when the
   forecaster is present and the lane has multi-period history.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest


# ── shared fixture ──────────────────────────────────────────────────────


def _entry(
    *,
    period: int,
    hs: str,
    dest: int,
    origin: int,
    cvs: float,
    his: float,
    notif: int,
    sci: float = 1.0,
    ocs: float = 0.4,
    bdi: float = 0.5,
    hhi: float = 0.4,
    idr: float = 0.7,
    mode: str = "sci_crs_his",
    commodity_name: str = "Mussels",
) -> dict[str, Any]:
    return {
        "commodity_hs": hs,
        "destination_m49": dest,
        "origin_m49": origin,
        "commodity_name": commodity_name,
        "destination_country": "France",
        "origin_country": "Spain",
        "period": period,
        "cvs": cvs,
        "cvs_mode": mode,
        "his": his,
        "sci": sci,
        "ocs": ocs,
        "bdi": bdi,
        "hhi": hhi,
        "idr": idr,
        "notification_count": notif,
        "severity_total": float(notif),
        "hdi": 0.1,
        "market_presence": "confirmed",
        "provenance": "faostat",
        "idr_gt_1": False,
        "bilateral_import_kg": 1_000_000.0,
    }


def _fitted_state() -> SimpleNamespace:
    """State with 4 periods × 15 lanes and a fitted LightGBM forecaster."""
    from defensefood.agent.predictive.lightgbm_forecaster import LightGBMForecaster
    from defensefood.agent.predictive.eval_harness import prepare_forecaster

    lanes_30 = [
        ("30771", 250, 724), ("30772", 250, 380), ("30773", 250, 528),
        ("30774", 250, 56),  ("30781", 250, 620), ("30782", 250, 372),
        ("30791", 250, 826),
    ]
    lanes_10 = [
        ("100590", 250, 724), ("100630", 250, 380), ("100640", 250, 528),
        ("100120", 250, 56),  ("100190", 250, 620), ("100210", 250, 372),
        ("100290", 250, 826), ("100300", 250, 700),
    ]
    scored: dict[int, dict[tuple[str, int, int], dict]] = {}
    for period in (2020, 2021, 2022, 2023):
        snap: dict[tuple[str, int, int], dict] = {}
        offset = period - 2020
        for hs, dest, origin in lanes_30:
            jitter = (hash(hs + str(origin)) % 7) * 0.005
            snap[(hs, dest, origin)] = _entry(
                period=period, hs=hs, dest=dest, origin=origin,
                cvs=min(0.9, 0.20 + 0.04 * offset + jitter),
                his=0.25 + 0.05 * offset, notif=1 + offset,
            )
        for hs, dest, origin in lanes_10:
            jitter = (hash(hs + str(origin)) % 7) * 0.005
            snap[(hs, dest, origin)] = _entry(
                period=period, hs=hs, dest=dest, origin=origin,
                cvs=0.15 + jitter, his=0.12, notif=offset, mode="sci_his",
                commodity_name="Rice",
            )
        scored[period] = snap

    corridor_metrics = []
    for (hs, dest, origin), entry in scored[2023].items():
        corridor_metrics.append(
            {
                "commodity_hs": hs,
                "destination_m49": dest,
                "origin_m49": origin,
                "commodity_name": entry["commodity_name"],
                "destination_country": entry["destination_country"],
                "origin_country": entry["origin_country"],
                "market_presence": entry["market_presence"],
            }
        )

    state = SimpleNamespace(
        scored_history=scored,
        corridor_metrics=corridor_metrics,
        notifications=[],
        forecaster=None,
        forecast_target_period=0,
    )
    forecaster = LightGBMForecaster(min_data_in_leaf=1, num_iterations=20)
    prepare_forecaster(state, forecaster=forecaster, train_periods=[2020, 2021, 2022])
    if getattr(forecaster, "_is_fit", False):
        state.forecaster = forecaster
        state.forecast_target_period = 2024
    return state


# ── tool: predict_lane_next_period ───────────────────────────────────────


def test_predict_tool_returns_forecast_for_lane_with_history():
    from defensefood.agent.tools import invoke_tool

    state = _fitted_state()
    assert state.forecaster is not None  # fixture sanity

    raw = invoke_tool(
        "predict_lane_next_period",
        {
            "commodity_hs": "30771",
            "destination_m49": 250,
            "origin_m49": 724,
        },
        state=state,
    )
    assert raw["ok"] is True
    result = raw["result"]
    assert result["ok"] is True
    assert result["target_period"] == 2024
    assert result["as_of_period"] == 2023
    assert result["cvs_point"] is not None
    assert 0.0 <= result["cvs_point"] <= 1.0
    assert result["cvs_low"] <= result["cvs_point"] <= result["cvs_high"]
    assert result["direction"] in ("rising", "falling", "stable")
    assert result["confidence"] in ("low", "med", "high")
    assert isinstance(result["drivers"], list)
    obs = result["observed"]
    assert obs["period"] == 2023
    assert obs["cvs"] is not None


def test_predict_tool_returns_unavailable_when_forecaster_missing():
    from defensefood.agent.tools import invoke_tool

    state = _fitted_state()
    state.forecaster = None

    raw = invoke_tool(
        "predict_lane_next_period",
        {
            "commodity_hs": "30771",
            "destination_m49": 250,
            "origin_m49": 724,
        },
        state=state,
    )
    assert raw["ok"] is True
    result = raw["result"]
    assert result["ok"] is False
    assert result["predictive_unavailable"] is True
    assert "trained" in result["reason"].lower()


def test_predict_tool_returns_no_history_for_unknown_lane():
    from defensefood.agent.tools import invoke_tool

    state = _fitted_state()
    raw = invoke_tool(
        "predict_lane_next_period",
        {
            "commodity_hs": "99999",
            "destination_m49": 250,
            "origin_m49": 999,
        },
        state=state,
    )
    assert raw["ok"] is True
    result = raw["result"]
    assert result["ok"] is False
    assert result["no_history"] is True


# ── HTTP endpoint ───────────────────────────────────────────────────────


def test_forecast_endpoint_returns_prediction_when_forecaster_ready(monkeypatch):
    from fastapi.testclient import TestClient
    from defensefood.api.main import app
    from defensefood.api import dependencies as deps

    deps._state = None
    monkeypatch.setattr(deps, "_load_data", lambda s: None)
    state = _fitted_state()
    deps._state = state

    client = TestClient(app)
    r = client.get("/api/v1/agent/forecast/30771/250/724")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["target_period"] == 2024
    assert body["cvs_point"] is not None


def test_forecast_endpoint_returns_unavailable_on_200_when_no_model(monkeypatch):
    """Frontend can render the 'model not available' state without a
    try/catch — the endpoint returns 200 with ok=false."""
    from fastapi.testclient import TestClient
    from defensefood.api.main import app
    from defensefood.api import dependencies as deps

    deps._state = None
    monkeypatch.setattr(deps, "_load_data", lambda s: None)
    state = _fitted_state()
    state.forecaster = None
    deps._state = state

    client = TestClient(app)
    r = client.get("/api/v1/agent/forecast/30771/250/724")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body.get("predictive_unavailable") is True


# ── anomaly explainer preload ──────────────────────────────────────────


def test_anomaly_preload_includes_model_outlook_when_forecaster_ready():
    """``_preload_anomaly_context`` calls the predict tool and stamps the
    result onto ``preload['model_outlook']``."""
    from defensefood.agent.briefs.anomaly_explainer import (
        _preload_anomaly_context,
    )

    state = _fitted_state()
    # AppState contracts the anomaly explainer reads from. Add the few
    # other fields it needs so the preload's other calls don't crash.
    state.dependency_history = {}
    state.notifications_by_corridor = {}
    state.coverage = {}

    corridor = state.corridor_metrics[0]
    preload = _preload_anomaly_context(
        state,
        corridor["commodity_hs"],
        int(corridor["destination_m49"]),
        int(corridor["origin_m49"]),
        corridor,
    )
    assert "model_outlook" in preload
    outlook = preload["model_outlook"]
    assert outlook["target_period"] == 2024
    assert outlook["cvs_point"] is not None
    assert outlook["confidence"] in ("low", "med", "high")


def test_anomaly_preload_skips_model_outlook_when_forecaster_missing():
    """No forecaster on state → preload doesn't carry a model_outlook key."""
    from defensefood.agent.briefs.anomaly_explainer import (
        _preload_anomaly_context,
    )

    state = _fitted_state()
    state.forecaster = None
    state.dependency_history = {}
    state.notifications_by_corridor = {}
    state.coverage = {}

    corridor = state.corridor_metrics[0]
    preload = _preload_anomaly_context(
        state,
        corridor["commodity_hs"],
        int(corridor["destination_m49"]),
        int(corridor["origin_m49"]),
        corridor,
    )
    assert "model_outlook" not in preload
