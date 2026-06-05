"""Phase 5.3 — anomaly explainer with mocked provider."""

from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace
from typing import Optional
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    db_path = tempfile.mktemp(suffix=".db")
    monkeypatch.setenv("DEFENSEFOOD_AGENT_DB_PATH", db_path)
    from defensefood.agent.config import reset_config_cache
    reset_config_cache()
    from defensefood.agent.cache import _INITIALIZED_DBS  # type: ignore[attr-defined]
    _INITIALIZED_DBS.clear()
    yield db_path
    try:
        os.unlink(db_path)
    except OSError:
        pass


from defensefood.agent.briefs import anomaly_explainer as a_mod
from defensefood.agent.briefs.schemas import (
    AnomalyExplanation,
    CitedSignal,
)
from defensefood.agent.provider import AgentRun


def _state_with_peers() -> SimpleNamespace:
    return SimpleNamespace(
        corridor_metrics=[
            {
                "commodity_hs": "30771",
                "commodity_name": "Mussels, frozen",
                "destination_m49": 250,
                "destination_country": "France",
                "origin_m49": 724,
                "origin_country": "Spain",
                "cvs": 0.345,
                "his": 0.42,
                "sci": 1.1,
                "hhi": 0.4,
                "ocs": 0.5,
                "idr": 0.7,
                "notification_count": 7,
                "cvs_mode": "sci_crs_his",
                "market_presence": "confirmed",
                "provenance": "faostat",
            },
            {
                # Peer at same chapter, same destination, same market_presence.
                "commodity_hs": "30772",
                "commodity_name": "Mussels, fresh",
                "destination_m49": 250,
                "destination_country": "France",
                "origin_m49": 380,
                "origin_country": "Italy",
                "cvs": 0.18,
                "his": 0.20,
                "sci": 0.9,
                "hhi": 0.35,
                "ocs": 0.45,
                "idr": 0.6,
                "notification_count": 2,
                "cvs_mode": "sci_crs_his",
                "market_presence": "confirmed",
                "provenance": "faostat",
            },
        ],
        coverage={"corridors_total": 2},
        dependency_history={
            2022: {("30771", 250, 724): {"cvs": 0.28, "sci": 1.0, "his": 0.40}},
            2023: {("30771", 250, 724): {"cvs": 0.345, "sci": 1.1, "his": 0.42}},
        },
        notifications_by_corridor={
            ("30771", 250, 724): [
                {"period": 202205},
                {"period": 202206},
                {"period": 202311},
                {"period": 202312},
            ],
        },
    )


def _explanation() -> AnomalyExplanation:
    return AnomalyExplanation(
        target_label="Spain mussels into France",
        verdict="anomalous",
        headline=(
            "Spain mussels into France stand out: Hazard Intensity Score (HIS) "
            "above peers and a rising CVS trend."
        ),
        why_anomalous=(
            "Composite Vulnerability Score (CVS) at 0.345 with a +0.065 shift "
            "from 2022 to 2023 puts this lane above peer mussel lanes into "
            "France. HIS of 0.42 is the highest in its peer set."
        ),
        why_not=(
            "Notification cadence is low (7 alerts across two years), and "
            "Origin Concentration Share (OCS) of 0.5 is in the moderate band, "
            "so the structural side does not by itself force the verdict."
        ),
        supporting_signals=[
            CitedSignal(name="CVS", source_field="cvs", value=0.345, band="med"),
            CitedSignal(name="HIS", source_field="his", value=0.42, band="med"),
        ],
        peer_comparison=(
            "Italian mussels into France carry CVS of 0.18 and HIS of 0.20; "
            "Spain's lane is roughly double on both axes."
        ),
        confidence="med",
        caveats=[],
    )


class _MockProvider:
    name = "anthropic"

    def __init__(self, expl: AnomalyExplanation) -> None:
        self._expl = expl
        self.calls: list[dict] = []

    def tool_use_loop(self, *, force_tool: Optional[str] = None, **kw) -> AgentRun:
        self.calls.append({"force": force_tool, "tools": kw.get("tool_names")})
        return AgentRun(
            final_text="",
            tool_traces=[],
            messages=[],
            tokens_in=1900,
            tokens_out=550,
            cost_usd=0.016,
            model="claude-sonnet-4-6",
            provider="anthropic",
            stop_reason="tool_use",
            structured_output=self._expl.model_dump(),
        )


def test_generates_explanation_with_peer_preload():
    state = _state_with_peers()
    prov = _MockProvider(_explanation())
    with patch.object(a_mod, "get_provider", return_value=prov):
        result = a_mod.generate_anomaly_explanation(
            "30771", 250, 724, state=state, verify="off"
        )
    assert result.explanation.verdict == "anomalous"
    # peer_comparison populated; exact phrasing is the model's choice.
    assert len(result.explanation.peer_comparison.strip()) > 0
    # Pre-loaded tools are not on the offered list.
    tools = prov.calls[0]["tools"]
    assert "get_corridor_profile" not in tools
    assert "interpret_metric_value" not in tools


def test_peer_summary_filters_by_chapter_destination_and_market_presence():
    """Internal peer summary excludes the self lane and lanes with different
    market_presence."""
    state = _state_with_peers()
    self_corridor = state.corridor_metrics[0]
    peers = a_mod._peer_summary(state, self_corridor)
    # Only the Italy peer should remain (same chapter '30', same dest 250,
    # same market_presence 'confirmed').
    assert len(peers) == 1
    assert peers[0]["origin_country"] == "Italy"


def test_required_caveats_for_single_period():
    """When the lane has fewer than 2 periods of snapshots, the single_period
    caveat is injected."""
    state = _state_with_peers()
    # Wipe 2022 → only 2023 snapshot remains.
    state.dependency_history = {2023: state.dependency_history[2023]}
    prov = _MockProvider(_explanation())
    with patch.object(a_mod, "get_provider", return_value=prov):
        result = a_mod.generate_anomaly_explanation(
            "30771", 250, 724, state=state, verify="fast"
        )
    joined = "\n".join(result.explanation.caveats).lower()
    assert "single-period" in joined or "cross-period drift" in joined


def test_style_sanitiser_strips_em_dashes_from_explanation():
    state = _state_with_peers()
    dirty = _explanation()
    dirty.why_anomalous = (
        "Spain mussels stand out — HIS is 0.42, the highest in peers."
    )
    dirty.why_not = "Notification cadence — low, only seven alerts."
    prov = _MockProvider(dirty)
    with patch.object(a_mod, "get_provider", return_value=prov):
        result = a_mod.generate_anomaly_explanation(
            "30771", 250, 724, state=state, verify="fast"
        )
    assert "—" not in result.explanation.why_anomalous
    assert "—" not in result.explanation.why_not


def test_only_cached_endpoint_returns_needs_generation():
    from fastapi.testclient import TestClient
    from defensefood.api.main import app
    import defensefood.api.dependencies as deps

    deps._state = None
    state = _state_with_peers()
    from defensefood.models.scores import ScoringConfig
    state.scoring_config = ScoringConfig()
    state.trade_period = 2023
    app.dependency_overrides[deps.get_state] = lambda: state

    def _explode(*a, **k):  # noqa: ARG001
        raise AssertionError("provider invoked on only_cached probe")

    client = TestClient(app)
    with patch.object(a_mod, "get_provider", side_effect=_explode):
        r = client.get(
            "/api/v1/agent/explain-anomaly/30771/250/724?only_cached=true"
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cache_hit"] is False
    assert body["needs_generation"] is True
    app.dependency_overrides.clear()
