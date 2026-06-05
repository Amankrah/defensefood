"""Phase 5.1 — hypothesis generator with mocked provider."""

from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace
from typing import Any, Optional
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


from defensefood.agent.briefs import hypotheses as h_mod
from defensefood.agent.briefs.schemas import (
    Hypothesis,
    HypothesisSet,
)
from defensefood.agent.provider import AgentRun


def _state() -> SimpleNamespace:
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
                "bdi": 0.6,
                "idr": 0.7,
                "notification_count": 7,
                "cvs_mode": "sci_crs_his",
                "market_presence": "confirmed",
                "provenance": "faostat",
            },
        ],
        coverage={"corridors_total": 1},
        dependency_history={
            2022: {("30771", 250, 724): {"cvs": 0.28, "sci": 1.0, "his": 0.40}},
            2023: {("30771", 250, 724): {"cvs": 0.345, "sci": 1.1, "his": 0.42}},
        },
        notifications_by_corridor={},
    )


def _hypothesis(headline: str = "Origin concentration grew because the second-largest supplier exited.") -> Hypothesis:
    return Hypothesis(
        headline=headline,
        narrative=(
            "Origin Concentration Share (OCS) of 0.5 with seven notifications "
            "matches a story where exits from the lane drove imports onto a "
            "single dominant supplier."
        ),
        confidence="med",
        supporting_evidence=[
            "OCS 0.5 (high band)",
            "HIS 0.42 (med band)",
        ],
        contradicting_evidence=[],
        falsifying_test=(
            "Run compare_periods on 2022 vs 2023 and confirm the "
            "second-largest supplier dropped out."
        ),
        next_data="Annual origin-share leaderboard from a trade-data provider.",
    )


def _set() -> HypothesisSet:
    return HypothesisSet(
        target_label="Spain mussels into France",
        pattern_summary="Lane carries watchlist-band CVS with seven RASFF alerts.",
        hypotheses=[
            _hypothesis(),
            _hypothesis(
                "Null hypothesis: the pattern matches peer behaviour and is not anomalous."
            ),
        ],
        caveats=[],
    )


class _MockProvider:
    name = "anthropic"

    def __init__(self, hset: HypothesisSet) -> None:
        self._hset = hset
        self.calls: list[dict] = []

    def tool_use_loop(self, *, force_tool: Optional[str] = None, **kw) -> AgentRun:
        self.calls.append({"force": force_tool, "tools": kw.get("tool_names")})
        return AgentRun(
            final_text="",
            tool_traces=[],
            messages=[],
            tokens_in=1800,
            tokens_out=500,
            cost_usd=0.015,
            model="claude-sonnet-4-6",
            provider="anthropic",
            stop_reason="tool_use",
            structured_output=self._hset.model_dump(),
        )


def test_generates_hypothesis_set_with_preload():
    state = _state()
    prov = _MockProvider(_set())
    with patch.object(h_mod, "get_provider", return_value=prov):
        result = h_mod.generate_hypotheses("30771", 250, 724, state=state, verify="off")
    assert result.hset.target_label == "Spain mussels into France"
    assert len(result.hset.hypotheses) == 2
    # Preload tools (corridor profile, notifications, interpretations) are NOT
    # offered to the agent.
    assert "get_corridor_profile" not in prov.calls[0]["tools"]
    assert "get_corridor_notifications" not in prov.calls[0]["tools"]
    assert "interpret_metric_value" not in prov.calls[0]["tools"]
    assert "submit_hypotheses" in prov.calls[0]["tools"]


def test_required_caveats_injected():
    """For an informational lane with cvs_mode=sci_his, both caveats appear."""
    state = _state()
    state.corridor_metrics[0]["market_presence"] = "informational"
    state.corridor_metrics[0]["cvs_mode"] = "sci_his"
    prov = _MockProvider(_set())
    with patch.object(h_mod, "get_provider", return_value=prov):
        result = h_mod.generate_hypotheses("30771", 250, 724, state=state, verify="fast")
    joined = "\n".join(result.hset.caveats).lower()
    assert "informational" in joined or "not placed" in joined
    assert "sci_his" in joined or "consumption demand" in joined


def test_style_sanitiser_strips_em_dashes_from_hypotheses():
    """Em-dashes in headlines and narratives get stripped during verify."""
    state = _state()
    dirty = _set()
    dirty.hypotheses[0].headline = (
        "Origin concentration grew — second-largest supplier exited."
    )
    dirty.hypotheses[0].narrative = (
        "OCS rose to 0.5 — driven by exits, not new entrants."
    )
    prov = _MockProvider(dirty)
    with patch.object(h_mod, "get_provider", return_value=prov):
        result = h_mod.generate_hypotheses("30771", 250, 724, state=state, verify="fast")
    assert "—" not in result.hset.hypotheses[0].headline
    assert "—" not in result.hset.hypotheses[0].narrative


def test_corridor_not_found_raises():
    state = _state()
    prov = _MockProvider(_set())
    with patch.object(h_mod, "get_provider", return_value=prov):
        with pytest.raises(ValueError, match="Corridor not found"):
            h_mod.generate_hypotheses("999", 1, 2, state=state, verify="off")


def test_hypothesis_validates_with_minimal_fields():
    """The flat Hypothesis shape: only headline + narrative are required; all
    other fields have safe defaults so partial drafts validate.
    """
    raw = {
        "headline": "Origin concentration rose because of a supplier exit.",
        "narrative": "OCS climbed from 0.4 to 0.5 between 2022 and 2023.",
        # no confidence, no evidence lists, no falsifying_test, no next_data
    }
    h = Hypothesis.model_validate(raw)
    assert h.confidence == "med"
    assert h.falsifying_test == ""
    assert h.next_data == ""
    assert h.supporting_evidence == []
    assert h.contradicting_evidence == []


def test_schema_rejects_empty_hypothesis_array_at_tool_layer():
    """Regression: the schema now marks hypotheses as required with
    min_length=2, so an empty array fails at Pydantic args validation
    before the tool function ever runs. The Anthropic API sees the schema's
    required list, which prevents the 'metadata-only submit' failure mode
    we hit in Phase 5.1.
    """
    from defensefood.agent.tools import invoke_tool

    state = _state()
    result = invoke_tool(
        "submit_hypotheses",
        {
            "target_label": "Spain mussels into France",
            "pattern_summary": "Watchlist-band CVS with sustained alerts.",
            "hypotheses": [],
        },
        state=state,
    )
    assert result["ok"] is False
    # Pydantic min_length error or tool-layer ValueError; either way the
    # error message must guide the model toward the 2-entry minimum.
    err = result["error"].lower()
    assert "at least 2" in err or "too_short" in err or "min" in err


def test_tool_layer_accepts_two_or_more_hypotheses():
    """A valid 2-hypothesis submission passes the tool layer."""
    from defensefood.agent.tools import invoke_tool

    state = _state()
    h1 = _hypothesis().model_dump()
    h2 = _hypothesis().model_dump()
    result = invoke_tool(
        "submit_hypotheses",
        {
            "target_label": "Spain mussels into France",
            "pattern_summary": "Watchlist-band CVS with sustained alerts.",
            "hypotheses": [h1, h2],
        },
        state=state,
    )
    assert result["ok"] is True
    assert len(result["result"]["hypotheses"]) == 2


def test_runner_surfaces_validation_error_in_failure_message():
    """When both passes fail validation, the runner reports the last error
    instead of the generic 'Provider may be unhealthy' message."""
    from defensefood.agent.briefs import hypotheses as h_mod
    from defensefood.agent.provider import AgentRun, ToolTrace
    from defensefood.agent.briefs.schemas import HypothesisSet

    state = _state()

    class _AlwaysFailsValidation:
        name = "anthropic"

        def __init__(self) -> None:
            self.calls: list[dict] = []

        def tool_use_loop(self, *, force_tool=None, **kw) -> AgentRun:
            self.calls.append({"force": force_tool})
            # Simulate the provider executing the tool and getting back an
            # ok=False validation error.
            failed_trace = ToolTrace(
                name="submit_hypotheses",
                args={},
                result={
                    "ok": False,
                    "error": "Argument validation failed: target_label required",
                },
                latency_ms=2,
            )
            return AgentRun(
                final_text="" if force_tool else "(some thinking)",
                tool_traces=[failed_trace],
                messages=[],
                tokens_in=500,
                tokens_out=200,
                cost_usd=0.005,
                model="claude-sonnet-4-6",
                provider="anthropic",
                stop_reason="tool_use" if not force_tool else "end_turn",
                structured_output=None,
            )

    prov = _AlwaysFailsValidation()
    with patch.object(h_mod, "get_provider", return_value=prov):
        with pytest.raises(RuntimeError, match="Last validation error"):
            h_mod.generate_hypotheses("30771", 250, 724, state=state, verify="off")


def test_only_cached_endpoint_returns_needs_generation():
    """The only_cached probe must not invoke the provider when nothing is cached."""
    from fastapi.testclient import TestClient
    from defensefood.api.main import app
    import defensefood.api.dependencies as deps

    deps._state = None
    state = _state()
    from defensefood.models.scores import ScoringConfig
    state.scoring_config = ScoringConfig()
    state.trade_period = 2023
    app.dependency_overrides[deps.get_state] = lambda: state

    def _explode(*a, **k):  # noqa: ARG001
        raise AssertionError("provider invoked on only_cached probe")

    client = TestClient(app)
    with patch.object(h_mod, "get_provider", side_effect=_explode):
        r = client.get(
            "/api/v1/agent/hypotheses/30771/250/724?only_cached=true"
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cache_hit"] is False
    assert body["needs_generation"] is True
    app.dependency_overrides.clear()
