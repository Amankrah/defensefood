"""Phase 1 — lane brief generator with a mocked provider.

Exercises the structured-output capture, reflection pass (signal mismatch
auto-correction, required-caveat injection), and the rerun path on hard
mismatches in strict mode. No live LLM keys required.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import patch

import pytest

# Ensure the cache singleton picks up a fresh temp DB per session.
@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    db_path = tempfile.mktemp(suffix=".db")
    monkeypatch.setenv("DEFENSEFOOD_AGENT_DB_PATH", db_path)
    from defensefood.agent.config import reset_config_cache
    reset_config_cache()
    # Reset the cache's lazy-init memo so the new path gets schema applied.
    from defensefood.agent.cache import _INITIALIZED_DBS  # type: ignore[attr-defined]
    _INITIALIZED_DBS.clear()
    yield db_path
    try:
        os.unlink(db_path)
    except OSError:
        pass


from defensefood.agent.briefs import lane_brief as lb_mod
from defensefood.agent.briefs.schemas import CitedSignal, LaneBrief
from defensefood.agent.provider import AgentRun, ToolTrace
from defensefood.agent.tools import invoke_tool


# ── golden corridor fixture ──────────────────────────────────────────────


def _golden_state() -> SimpleNamespace:
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
                "cvs": 0.345,
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
                "provenance": "faostat",
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
                "provenance": "trade_only",
            },
        ],
        coverage={"corridors_total": 2, "corridors_with_cvs": 2},
    )


# ── mock provider ────────────────────────────────────────────────────────


class _MockProvider:
    """Stand-in for an LLMProvider that returns a fixed structured output."""

    name = "anthropic"

    def __init__(
        self,
        *,
        brief: LaneBrief,
        cost_usd: float = 0.012,
        tokens_in: int = 1500,
        tokens_out: int = 400,
        emit_tools: Optional[list[tuple[str, dict[str, Any]]]] = None,
    ) -> None:
        self._brief = brief
        self._cost = cost_usd
        self._tin = tokens_in
        self._tout = tokens_out
        self._emit_tools = emit_tools or []
        self.calls: list[dict] = []

    def tool_use_loop(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tool_names: list[str],
        state: Any,
        tier: str = "narrative",
        max_iters: int = 8,
        max_tokens: int = 2048,
        temperature: float = 0.3,
        force_tool: Optional[str] = None,
    ) -> AgentRun:
        self.calls.append(
            {"user": user_prompt, "tools": tool_names, "force": force_tool}
        )
        # Simulate informative tool calls so the trace is non-empty.
        traces: list[ToolTrace] = []
        for tname, targs in self._emit_tools:
            raw = invoke_tool(tname, targs, state=state)
            traces.append(
                ToolTrace(name=tname, args=targs, result=raw, latency_ms=4)
            )
        return AgentRun(
            final_text="",
            tool_traces=traces,
            messages=[],
            tokens_in=self._tin,
            tokens_out=self._tout,
            cost_usd=self._cost,
            model="claude-sonnet-4-6",
            provider="anthropic",
            stop_reason="tool_use",
            structured_output=self._brief.model_dump(),
        )


def _make_brief(
    *,
    cvs_value: float = 0.345,
    his_value: float = 0.42,
    caveats: Optional[list[str]] = None,
    body_extra: str = "",
) -> LaneBrief:
    """Build a baseline LaneBrief used by the mock provider."""
    return LaneBrief(
        headline="Spanish mussels into France carry watchlist-band priority.",
        body_markdown=(
            "CVS sits at 0.345 driven by SCI 1.1 and 7 alerts. "
            "HIS is 0.42 across the loaded years." + body_extra
        ),
        key_signals=[
            CitedSignal(name="Priority (CVS)", source_field="cvs", value=cvs_value, band="med"),
            CitedSignal(name="Hazard intensity", source_field="his", value=his_value, band="med"),
            CitedSignal(name="Notification count", source_field="notification_count", value=7, band="unknown"),
        ],
        caveats=caveats or [],
        confidence="med",
    )


# ── tests ────────────────────────────────────────────────────────────────


def test_lane_brief_generates_and_verifies_clean_brief():
    """Happy path: brief signals match engine → no verifier corrections."""
    state = _golden_state()
    mock = _MockProvider(
        brief=_make_brief(),
        emit_tools=[
            ("get_corridor_profile", {"commodity_hs": "30771", "destination_m49": 250, "origin_m49": 724}),
            ("interpret_metric_value", {"metric_key": "cvs", "value": 0.345}),
        ],
    )
    with patch.object(lb_mod, "get_provider", return_value=mock):
        result = lb_mod.generate_lane_brief(
            "30771", 250, 724, state=state, verify="strict"
        )
    assert result.brief.headline.startswith("Spanish mussels")
    assert result.brief.confidence == "med"
    assert len(result.brief.key_signals) == 3
    # No mismatches → no notes about engine values (caveat injections are OK).
    hard_notes = [n for n in result.brief.verifier_notes if "engine has" in n]
    assert hard_notes == []


def test_verifier_auto_corrects_meaningful_numerical_drift():
    """Brief claims cvs=0.40 but engine has 0.345 (16% drift) → auto-correct.

    Drift below the 2% relative-tolerance floor is ignored as rounding noise.
    """
    state = _golden_state()
    drifted = _make_brief(cvs_value=0.40)
    mock = _MockProvider(brief=drifted)
    with patch.object(lb_mod, "get_provider", return_value=mock):
        result = lb_mod.generate_lane_brief(
            "30771", 250, 724, state=state, verify="strict"
        )
    cvs_sig = next(s for s in result.brief.key_signals if s.source_field == "cvs")
    assert abs(float(cvs_sig.value) - 0.345) < 1e-6
    assert any("cvs" in n for n in result.brief.verifier_notes)


def test_verifier_ignores_sub_two_percent_rounding_drift():
    """Drift inside the tolerance band must not trigger rerun or correction."""
    state = _golden_state()
    drifted = _make_brief(cvs_value=0.35)  # 1.4% relative drift, below 2%
    mock = _MockProvider(brief=drifted)
    with patch.object(lb_mod, "get_provider", return_value=mock):
        result = lb_mod.generate_lane_brief(
            "30771", 250, 724, state=state, verify="strict"
        )
    # No correction → the value stays as the model wrote it.
    cvs_sig = next(s for s in result.brief.key_signals if s.source_field == "cvs")
    assert abs(float(cvs_sig.value) - 0.35) < 1e-6
    # Only one provider call (no rerun).
    assert len(mock.calls) == 1


def test_verifier_injects_required_caveat_for_informational_lane():
    """Informational-only lane forces an informational caveat to appear."""
    state = _golden_state()
    # Brief about the rice lane (informational); the model omits the caveat.
    brief = LaneBrief(
        headline="Italian rice into France sits at watchlist band.",
        body_markdown="CVS is 0.18 with HIS 0.12.",
        key_signals=[
            CitedSignal(name="CVS", source_field="cvs", value=0.18, band="low"),
            CitedSignal(name="HIS", source_field="his", value=0.12, band="low"),
        ],
        caveats=[],  # missing required informational caveat
        confidence="low",
    )
    mock = _MockProvider(brief=brief)
    with patch.object(lb_mod, "get_provider", return_value=mock):
        result = lb_mod.generate_lane_brief(
            "100630", 250, 380, state=state, verify="strict"
        )
    # An informational caveat must now appear.
    assert any(
        "informational" in c.lower() or "not placed" in c.lower()
        for c in result.brief.caveats
    )
    # And: trade_only provenance caveat for this lane too.
    assert any("trade-only" in c.lower() or "trade_only" in c.lower() for c in result.brief.caveats)


def test_verifier_off_skips_signal_check():
    """verify='off' bypasses signal verification entirely."""
    state = _golden_state()
    # Brief lies about CVS being 1.0 — but with verify=off, nothing checks.
    brief = _make_brief(cvs_value=1.0)
    mock = _MockProvider(brief=brief)
    with patch.object(lb_mod, "get_provider", return_value=mock):
        result = lb_mod.generate_lane_brief(
            "30771", 250, 724, state=state, verify="off"
        )
    cvs_sig = next(s for s in result.brief.key_signals if s.source_field == "cvs")
    assert float(cvs_sig.value) == 1.0
    assert result.brief.verifier_notes == []


def test_unknown_corridor_raises():
    state = _golden_state()
    mock = _MockProvider(brief=_make_brief())
    with patch.object(lb_mod, "get_provider", return_value=mock):
        with pytest.raises(ValueError, match="Corridor not found"):
            lb_mod.generate_lane_brief("X", 1, 2, state=state)


def test_cost_and_metadata_propagate():
    state = _golden_state()
    mock = _MockProvider(brief=_make_brief(), cost_usd=0.0234, tokens_in=1234, tokens_out=345)
    with patch.object(lb_mod, "get_provider", return_value=mock):
        result = lb_mod.generate_lane_brief(
            "30771", 250, 724, state=state, verify="off"
        )
    assert result.cost_usd == pytest.approx(0.0234)
    assert result.tokens_in == 1234
    assert result.tokens_out == 345
    assert result.model == "claude-sonnet-4-6"
    assert result.provider == "anthropic"
    assert result.corridor_key == "30771/250/724"


# ── endpoint smoke (no streaming) ────────────────────────────────────────


def test_lane_brief_endpoint_caches_via_sqlite():
    """Two consecutive calls hit the SQLite cache on the second one."""
    from fastapi.testclient import TestClient
    from defensefood.api.main import app
    import defensefood.api.dependencies as deps

    deps._state = None  # force a fresh state lookup
    # Replace the real state lookup with our golden fixture.
    state = _golden_state()
    # Add the snapshot-hash-feeding attributes the endpoint reads.
    from defensefood.models.scores import ScoringConfig
    state.scoring_config = ScoringConfig()
    state.trade_period = 2023

    def _state_provider():
        return state

    app.dependency_overrides[deps.get_state] = _state_provider

    mock = _MockProvider(brief=_make_brief())
    client = TestClient(app)

    with patch.object(lb_mod, "get_provider", return_value=mock):
        r1 = client.get("/api/v1/agent/lane-brief/30771/250/724?verify=off")
        assert r1.status_code == 200, r1.text
        body1 = r1.json()
        assert body1["brief"]["headline"].startswith("Spanish mussels")

        # Second call returns the cached version (the brief shape includes a cache_hit flag).
        r2 = client.get("/api/v1/agent/lane-brief/30771/250/724?verify=off")
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2.get("cache_hit") is True
        # Cached payload preserves the headline.
        assert body2["brief"]["headline"] == body1["brief"]["headline"]

    app.dependency_overrides.clear()


# ── pre-loaded data block ────────────────────────────────────────────────


def test_preload_block_embedded_in_user_prompt():
    """The mock provider receives the pre-loaded data in the user prompt and
    therefore does not need to call get_corridor_profile etc."""
    state = _golden_state()
    mock = _MockProvider(brief=_make_brief())
    with patch.object(lb_mod, "get_provider", return_value=mock):
        lb_mod.generate_lane_brief(
            "30771", 250, 724, state=state, verify="off"
        )
    # The very first provider call must carry the preload markers.
    assert len(mock.calls) == 1
    first_user = mock.calls[0]["user"]
    assert "Pre-loaded lane data" in first_user
    assert '"profile"' in first_user
    assert '"metric_bands"' in first_user
    # The metric bands cover at least cvs and his for the Spain mussels lane.
    assert '"cvs"' in first_user
    assert '"his"' in first_user


def test_preload_tool_surface_excludes_redundant_lookups():
    """The lane brief no longer offers get_corridor_profile /
    get_corridor_notifications / interpret_metric_value to the agent."""
    state = _golden_state()
    mock = _MockProvider(brief=_make_brief())
    with patch.object(lb_mod, "get_provider", return_value=mock):
        lb_mod.generate_lane_brief(
            "30771", 250, 724, state=state, verify="off"
        )
    offered = mock.calls[0]["tools"]
    assert "get_corridor_profile" not in offered
    assert "get_corridor_notifications" not in offered
    assert "interpret_metric_value" not in offered
    # Submit tool is still there.
    assert "submit_lane_brief" in offered


# ── style scanner ────────────────────────────────────────────────────────


def test_style_sanitiser_strips_em_dashes_and_flags_phrases():
    """Em-dashes get replaced; forbidden phrases get flagged in notes."""
    from defensefood.agent.briefs.lane_brief import _sanitise_style

    src = (
        "Spain to Italy mussels — the strongest hazard lane — drove the queue. "
        "Critically, alerts ran across every loaded year, consistent with "
        "seasonal harvesting."
    )
    cleaned, notes = _sanitise_style(src)
    assert "—" not in cleaned
    assert "Spain to Italy mussels, the strongest hazard lane, drove the queue" in cleaned
    # Forbidden phrases get logged but the text is left so the model self-corrects.
    joined = "\n".join(notes)
    assert "critically," in joined.lower()
    assert "consistent with" in joined.lower()


def test_style_sanitiser_runs_through_full_brief_pipeline():
    """End-to-end: a brief with em-dashes gets cleaned during verify."""
    state = _golden_state()
    dirty = LaneBrief(
        headline="Spanish mussels into France — strongest hazard lane.",
        body_markdown=(
            "CVS sits at 0.345 — driven by SCI 1.1 and 7 alerts. "
            "Critically, HIS is 0.42 across the loaded years."
        ),
        key_signals=[
            CitedSignal(name="CVS", source_field="cvs", value=0.345, band="med"),
            CitedSignal(name="HIS", source_field="his", value=0.42, band="med"),
            CitedSignal(name="Alerts", source_field="notification_count", value=7, band="unknown"),
        ],
        caveats=[],
        confidence="med",
    )
    mock = _MockProvider(brief=dirty)
    with patch.object(lb_mod, "get_provider", return_value=mock):
        result = lb_mod.generate_lane_brief(
            "30771", 250, 724, state=state, verify="fast"
        )
    assert "—" not in result.brief.headline
    assert "—" not in result.brief.body_markdown
    # Note: the prompt forbids "Critically,"; verifier records the violation.
    style_notes = [n for n in result.brief.verifier_notes if n.startswith("style:")]
    assert any("em/en-dash" in n for n in style_notes)
    assert any("critically," in n.lower() for n in style_notes)


# ── force_tool fallback ──────────────────────────────────────────────────


class _TextThenForcedProvider:
    """Mock provider that returns prose on the first call and structured output
    only when ``force_tool="submit_lane_brief"`` is set.

    Reproduces the failure mode where the agent ends with text instead of the
    forced submit; the generator should detect that and retry with force_tool.
    """

    name = "anthropic"

    def __init__(self, *, fallback_brief: LaneBrief) -> None:
        self._brief = fallback_brief
        self.calls: list[dict] = []

    def tool_use_loop(self, *, force_tool: Optional[str] = None, **kw) -> AgentRun:
        self.calls.append({"force": force_tool, "tools": kw.get("tool_names")})
        if force_tool == "submit_lane_brief":
            return AgentRun(
                final_text="",
                tool_traces=[],
                messages=[],
                tokens_in=200,
                tokens_out=150,
                cost_usd=0.001,
                model="claude-sonnet-4-6",
                provider="anthropic",
                stop_reason="tool_use",
                structured_output=self._brief.model_dump(),
            )
        # Without force, simulate the buggy path: prose, no structured output.
        return AgentRun(
            final_text=(
                "I would summarise that CVS for this lane sits at 0.345 with "
                "watchlist-band priority, driven by SCI 1.1 and 7 alerts."
            ),
            tool_traces=[],
            messages=[],
            tokens_in=1500,
            tokens_out=400,
            cost_usd=0.012,
            model="claude-sonnet-4-6",
            provider="anthropic",
            stop_reason="end_turn",
            structured_output=None,
        )


def test_force_tool_fallback_recovers_when_first_pass_ends_with_text():
    """The first pass ends with text; the fallback forces submit_lane_brief
    and the brief comes through with merged token counts."""
    state = _golden_state()
    provider = _TextThenForcedProvider(fallback_brief=_make_brief())
    with patch.object(lb_mod, "get_provider", return_value=provider):
        result = lb_mod.generate_lane_brief(
            "30771", 250, 724, state=state, verify="off"
        )
    # Two calls: original draft + forced retry.
    assert len(provider.calls) == 2
    assert provider.calls[0]["force"] is None
    assert provider.calls[1]["force"] == "submit_lane_brief"
    assert provider.calls[1]["tools"] == ["submit_lane_brief"]
    # Final brief is the structured one returned by the forced pass.
    assert result.brief.headline.startswith("Spanish mussels")
    # Cost / tokens merged across both passes.
    assert result.tokens_in == 1500 + 200
    assert result.tokens_out == 400 + 150
    assert result.cost_usd == pytest.approx(0.012 + 0.001)


class _AlwaysTextProvider:
    """Provider that NEVER submits, even under force_tool. Tests the
    ultimate-failure path."""

    name = "anthropic"

    def tool_use_loop(self, *, force_tool: Optional[str] = None, **kw) -> AgentRun:
        return AgentRun(
            final_text="(text, no submit ever)",
            tool_traces=[],
            messages=[],
            tokens_in=100,
            tokens_out=50,
            cost_usd=0.001,
            model="claude-sonnet-4-6",
            provider="anthropic",
            stop_reason="end_turn",
            structured_output=None,
        )


def test_force_tool_fallback_raises_when_provider_keeps_failing():
    """Both passes return text → RuntimeError surfaces to the endpoint."""
    state = _golden_state()
    with patch.object(lb_mod, "get_provider", return_value=_AlwaysTextProvider()):
        with pytest.raises(RuntimeError, match="forced tool choice"):
            lb_mod.generate_lane_brief("30771", 250, 724, state=state, verify="off")


# ── only_cached endpoint ─────────────────────────────────────────────────


def test_only_cached_returns_needs_generation_without_calling_provider():
    """only_cached=true must not invoke the provider when no cache row exists."""
    from fastapi.testclient import TestClient
    from defensefood.api.main import app
    import defensefood.api.dependencies as deps

    deps._state = None
    state = _golden_state()
    from defensefood.models.scores import ScoringConfig
    state.scoring_config = ScoringConfig()
    state.trade_period = 2023

    app.dependency_overrides[deps.get_state] = lambda: state

    # Patch get_provider so that any LLM call would explode loudly. The test
    # asserts only_cached short-circuits before reaching it.
    def _explode(*a, **k):  # noqa: ARG001
        raise AssertionError("provider invoked on only_cached probe")

    client = TestClient(app)
    with patch.object(lb_mod, "get_provider", side_effect=_explode):
        r = client.get(
            "/api/v1/agent/lane-brief/30771/250/724?only_cached=true&verify=off"
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cache_hit"] is False
    assert body["needs_generation"] is True
    assert body["target_key"] == "30771/250/724"
    assert "snapshot_hash" in body

    app.dependency_overrides.clear()


def test_only_cached_returns_brief_when_cache_hits():
    """After a first call populates cache, only_cached returns the stored brief."""
    from fastapi.testclient import TestClient
    from defensefood.api.main import app
    import defensefood.api.dependencies as deps

    deps._state = None
    state = _golden_state()
    from defensefood.models.scores import ScoringConfig
    state.scoring_config = ScoringConfig()
    state.trade_period = 2023

    app.dependency_overrides[deps.get_state] = lambda: state

    mock = _MockProvider(brief=_make_brief())
    client = TestClient(app)
    with patch.object(lb_mod, "get_provider", return_value=mock):
        # Populate cache.
        r1 = client.get("/api/v1/agent/lane-brief/30771/250/724?verify=off")
        assert r1.status_code == 200

    # Now only_cached must hit, with no provider invocation.
    def _explode(*a, **k):  # noqa: ARG001
        raise AssertionError("provider invoked on only_cached after cache populated")

    with patch.object(lb_mod, "get_provider", side_effect=_explode):
        r2 = client.get(
            "/api/v1/agent/lane-brief/30771/250/724?only_cached=true&verify=off"
        )
    assert r2.status_code == 200
    body = r2.json()
    assert body["cache_hit"] is True
    assert body["brief"]["headline"].startswith("Spanish mussels")

    app.dependency_overrides.clear()
