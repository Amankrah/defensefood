"""Phase 1 agent tools — schema generation, dispatch, validation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from defensefood.agent import tools as agent_tools


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def fake_state() -> SimpleNamespace:
    """Minimal AppState stand-in: just corridor_metrics + coverage."""
    return SimpleNamespace(
        corridor_metrics=[
            {
                "commodity_hs": "30771",
                "commodity_name": "Mussels, frozen",
                "destination_m49": 250,
                "destination_country": "France",
                "origin_m49": 724,
                "origin_country": "Spain",
                "his": 0.42,
                "hdi": 0.31,
                "cvs": 0.35,
                "cvs_mode": "sci_crs_his",
                "sci": 1.1,
                "bdi": 0.6,
                "idr": 0.7,
                "ocs": 0.5,
                "hhi": 0.4,
                "notification_count": 7,
                "severity_total": 4.2,
                "market_presence": "confirmed",
                "destination_roles": ["distribution", "followUp"],
                "data_quality": "full",
            },
            {
                "commodity_hs": "100630",
                "commodity_name": "Semi-milled rice",
                "destination_m49": 250,
                "destination_country": "France",
                "origin_m49": 380,
                "origin_country": "Italy",
                "his": 0.12,
                "hdi": 0.05,
                "cvs": 0.18,
                "cvs_mode": "sci_his",
                "notification_count": 2,
                "market_presence": "informational",
                "data_quality": "partial",
            },
        ],
        coverage={"corridors_total": 2, "corridors_with_cvs": 2},
    )


# ── tool registry shape ──────────────────────────────────────────────────


def test_tool_registry_has_all_expected_names():
    """The 14 tools (13 in tools.py + submit_lane_brief from briefs/) are registered."""
    # Import the brief to trigger submit_lane_brief registration.
    from defensefood.agent.briefs import lane_brief  # noqa: F401

    expected = {
        "get_corridor_profile",
        "list_top_corridors",
        "get_methodology",
        "interpret_metric_value",
        "country_inbound_exposure",
        "country_outbound_orps",
        "get_hazard_summary",
        "get_corridor_notifications",
        "get_hazard_probability",
        "get_trade_anomalies",
        "get_corridor_time_series",
        "compare_periods",
        "get_data_coverage",
        "submit_lane_brief",
    }
    missing = expected - set(agent_tools.TOOL_REGISTRY.keys())
    assert not missing, f"missing tools: {missing}"


def test_anthropic_schemas_compile():
    """All registered tools produce a JSON Schema that round-trips through json.dumps."""
    import json

    payload = agent_tools.anthropic_schemas()
    json.dumps(payload)  # raises if any schema entry isn't serialisable
    assert all("name" in s and "input_schema" in s for s in payload)


def test_openai_schemas_compile():
    import json

    payload = agent_tools.openai_schemas()
    json.dumps(payload)
    assert all(s["type"] == "function" and "function" in s for s in payload)


# ── individual tool dispatch ─────────────────────────────────────────────


def test_get_corridor_profile_found(fake_state):
    r = agent_tools.invoke_tool(
        "get_corridor_profile",
        {"commodity_hs": "30771", "destination_m49": 250, "origin_m49": 724},
        state=fake_state,
    )
    assert r["ok"] is True
    assert r["result"]["found"] is True
    assert r["result"]["cvs"] == 0.35


def test_get_corridor_profile_not_found(fake_state):
    r = agent_tools.invoke_tool(
        "get_corridor_profile",
        {"commodity_hs": "999999", "destination_m49": 1, "origin_m49": 2},
        state=fake_state,
    )
    assert r["ok"] is True
    assert r["result"]["found"] is False


def test_list_top_corridors_sorts_by_cvs(fake_state):
    r = agent_tools.invoke_tool(
        "list_top_corridors", {"by": "cvs", "n": 2}, state=fake_state
    )
    assert r["ok"] is True
    rows = r["result"]
    assert len(rows) == 2
    assert rows[0]["cvs"] >= rows[1]["cvs"]


def test_list_top_corridors_filter_market_presence(fake_state):
    r = agent_tools.invoke_tool(
        "list_top_corridors",
        {"by": "cvs", "n": 10, "market_presence": "confirmed"},
        state=fake_state,
    )
    rows = r["result"]
    assert len(rows) == 1
    assert rows[0]["market_presence"] == "confirmed"


def test_interpret_metric_value(fake_state):
    r = agent_tools.invoke_tool(
        "interpret_metric_value",
        {"metric_key": "cvs", "value": 0.32},
        state=fake_state,
    )
    assert r["ok"] is True
    assert r["result"]["band"] in {"low", "med", "high", "flag"}
    assert r["result"]["ok"] is True


def test_get_methodology_known_key(fake_state):
    r = agent_tools.invoke_tool(
        "get_methodology", {"metric_key": "cvs"}, state=fake_state
    )
    assert r["ok"] is True
    assert r["result"]["found"] is True
    assert r["result"]["section"] == "7"


def test_get_methodology_unknown_key(fake_state):
    r = agent_tools.invoke_tool(
        "get_methodology", {"metric_key": "not_a_metric"}, state=fake_state
    )
    assert r["ok"] is True
    assert r["result"]["found"] is False


# ── validation + error handling ───────────────────────────────────────────


def test_validation_error_returned_as_payload(fake_state):
    """Bad args don't raise — they return {ok: False, error: ...}."""
    r = agent_tools.invoke_tool(
        "get_corridor_profile",
        {"commodity_hs": "30771"},  # missing two required fields
        state=fake_state,
    )
    assert r["ok"] is False
    assert "validation" in r["error"].lower()


def test_unknown_tool_returned_as_payload(fake_state):
    r = agent_tools.invoke_tool("does_not_exist", {}, state=fake_state)
    assert r["ok"] is False
    assert "unknown" in r["error"].lower()


# ── decorator hygiene ─────────────────────────────────────────────────────


def test_decorator_rejects_function_without_pydantic_args():
    """Tools whose first arg isn't a BaseModel get a clear TypeError at decoration."""
    with pytest.raises(TypeError, match="Pydantic"):
        @agent_tools.tool(name="_test_bad_decl")
        def bad(args: dict, *, state: Any) -> dict:  # noqa: ARG001
            return {}
