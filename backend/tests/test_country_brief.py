"""Phase 2 — country brief generator with a multi-agent mocked provider.

Exercises:
  * The parallel sub-agent dispatch (inbound + outbound run in a thread pool).
  * The synthesiser composing both halves into a CountryBrief.
  * Reflection: band consistency check + country-level caveat aggregator.
  * Hand-merge fallback when the synthesiser fails to submit.
  * Outbound-only and inbound-only short-circuit paths.
"""

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


from defensefood.agent.briefs import country_brief as cb_mod
from defensefood.agent.briefs.schemas import (
    CitedSignal,
    CountryBrief,
    CountryHalf,
)
from defensefood.agent.provider import AgentRun, ToolTrace
from defensefood.agent.tools import invoke_tool


# ── fixtures ──────────────────────────────────────────────────────────────


def _golden_state() -> SimpleNamespace:
    return SimpleNamespace(
        corridor_metrics=[
            # France as destination (inbound)
            {
                "commodity_hs": "30771",
                "commodity_name": "Mussels",
                "destination_m49": 250,
                "destination_country": "France",
                "origin_m49": 724,
                "origin_country": "Spain",
                "his": 0.42,
                "acep": None,
                "cvs": 0.345,
                "cvs_mode": "sci_crs_his",
                "notification_count": 7,
                "market_presence": "confirmed",
            },
            {
                "commodity_hs": "100630",
                "commodity_name": "Rice",
                "destination_m49": 250,
                "destination_country": "France",
                "origin_m49": 380,
                "origin_country": "Italy",
                "his": 0.12,
                "cvs": 0.18,
                "cvs_mode": "sci_his",
                "notification_count": 2,
                "market_presence": "informational",
            },
            # France as origin (outbound)
            {
                "commodity_hs": "100590",
                "commodity_name": "Maize",
                "destination_m49": 56,
                "destination_country": "Belgium",
                "origin_m49": 250,
                "origin_country": "France",
                "his": 0.21,
                "cvs": 0.24,
                "cvs_mode": "sci_crs_his",
                "notification_count": 3,
                "market_presence": "confirmed",
            },
        ],
    )


# ── mock provider that returns different shaped outputs per phase ─────────


class _MultiCallProvider:
    """Returns scripted structured outputs based on which submit tool is forced."""

    name = "anthropic"

    def __init__(
        self,
        inbound: CountryHalf,
        outbound: CountryHalf,
        synthesised: Optional[CountryBrief] = None,
        cost: float = 0.005,
    ):
        self._inbound = inbound
        self._outbound = outbound
        self._synth = synthesised
        self._cost = cost
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
        # Determine which phase this call is by inspecting the tool list.
        if "submit_inbound_half" in tool_names:
            output = self._inbound.model_dump()
            phase = "inbound"
        elif "submit_outbound_half" in tool_names:
            output = self._outbound.model_dump()
            phase = "outbound"
        elif "submit_country_brief" in tool_names:
            output = self._synth.model_dump() if self._synth else None
            phase = "synthesiser"
        else:
            output = None
            phase = "unknown"
        self.calls.append(
            {"phase": phase, "tools": tool_names, "force": force_tool}
        )
        # Synthesise a tool trace so cost aggregation works.
        return AgentRun(
            final_text="",
            tool_traces=[ToolTrace(name="dummy", args={}, result={"ok": True}, latency_ms=2)],
            messages=[],
            tokens_in=300,
            tokens_out=100,
            cost_usd=self._cost,
            model="claude-sonnet-4-6",
            provider="anthropic",
            stop_reason="tool_use",
            structured_output=output,
        )


# ── helpers ───────────────────────────────────────────────────────────────


def _basic_inbound_half() -> CountryHalf:
    return CountryHalf(
        markdown="France faces concentrated inbound pressure from Spanish mussels.",
        signals=[
            CitedSignal(name="ACEP", source_field="acep", value=0.62, band="med"),
            CitedSignal(name="Top inbound HIS", source_field="his", value=0.42, band="med"),
        ],
        notable_lanes=["30771/250/724"],
    )


def _basic_outbound_half() -> CountryHalf:
    return CountryHalf(
        markdown="France propagates exposure outward via maize to Belgium.",
        signals=[
            CitedSignal(name="Maize ORPS", source_field="orps", value=0.35, band="med"),
        ],
        notable_lanes=["100590/56/250"],
    )


def _basic_synth() -> CountryBrief:
    return CountryBrief(
        headline="France: heavy inbound pressure (Spanish mussels) and material outbound maize propagation.",
        inbound_markdown="France faces concentrated inbound pressure from Spanish mussels.",
        outbound_markdown="France propagates exposure outward via maize to Belgium.",
        key_signals=[
            CitedSignal(name="ACEP", source_field="acep", value=0.62, band="med"),
            CitedSignal(name="Top inbound HIS", source_field="his", value=0.42, band="med"),
            CitedSignal(name="Maize ORPS", source_field="orps", value=0.35, band="med"),
        ],
        notable_lanes=["30771/250/724", "100590/56/250"],
        caveats=[],
        confidence="med",
    )


# ── tests ────────────────────────────────────────────────────────────────


def test_full_pipeline_runs_inbound_outbound_synth():
    state = _golden_state()
    provider = _MultiCallProvider(
        inbound=_basic_inbound_half(),
        outbound=_basic_outbound_half(),
        synthesised=_basic_synth(),
    )
    with patch.object(cb_mod, "get_provider", return_value=provider):
        result = cb_mod.generate_country_brief(250, state=state, verify="off")
    # Three sub-agent calls expected.
    phases = [c["phase"] for c in provider.calls]
    assert "inbound" in phases
    assert "outbound" in phases
    assert "synthesiser" in phases
    assert result.brief.inbound_markdown
    assert result.brief.outbound_markdown
    assert len(result.brief.key_signals) == 3
    # Cost aggregation = three sub-calls × 0.005
    assert result.cost_usd == pytest.approx(0.015, abs=1e-6)


def test_skip_outbound_when_no_outbound_corridors():
    """A pure-destination country skips the outbound specialist."""
    state = _golden_state()
    # Strip outbound corridors so France only appears as destination.
    state.corridor_metrics = [
        c for c in state.corridor_metrics if int(c.get("origin_m49") or -1) != 250
    ]
    provider = _MultiCallProvider(
        inbound=_basic_inbound_half(),
        outbound=_basic_outbound_half(),  # never used
        synthesised=_basic_synth(),
    )
    with patch.object(cb_mod, "get_provider", return_value=provider):
        result = cb_mod.generate_country_brief(250, state=state, verify="off")
    phases = [c["phase"] for c in provider.calls]
    assert "outbound" not in phases
    assert any("outbound specialist skipped" in n for n in result.brief.sub_agent_notes)


def test_skip_inbound_when_no_inbound_corridors():
    """A pure-origin country skips the inbound specialist."""
    state = _golden_state()
    state.corridor_metrics = [
        c for c in state.corridor_metrics if int(c.get("destination_m49") or -1) != 250
    ]
    provider = _MultiCallProvider(
        inbound=_basic_inbound_half(),
        outbound=_basic_outbound_half(),
        synthesised=_basic_synth(),
    )
    with patch.object(cb_mod, "get_provider", return_value=provider):
        result = cb_mod.generate_country_brief(250, state=state, verify="off")
    phases = [c["phase"] for c in provider.calls]
    assert "inbound" not in phases
    assert any("inbound specialist skipped" in n for n in result.brief.sub_agent_notes)


def test_raises_when_country_has_no_corridors():
    state = _golden_state()
    provider = _MultiCallProvider(
        inbound=_basic_inbound_half(),
        outbound=_basic_outbound_half(),
        synthesised=_basic_synth(),
    )
    with patch.object(cb_mod, "get_provider", return_value=provider):
        with pytest.raises(ValueError, match="No corridors"):
            cb_mod.generate_country_brief(9999, state=state)


def test_hand_merge_fallback_when_synth_fails():
    """If the synthesiser doesn't submit, we hand-merge the halves."""
    state = _golden_state()
    provider = _MultiCallProvider(
        inbound=_basic_inbound_half(),
        outbound=_basic_outbound_half(),
        synthesised=None,  # synthesiser returns None
    )
    with patch.object(cb_mod, "get_provider", return_value=provider):
        result = cb_mod.generate_country_brief(250, state=state, verify="off")
    assert any("hand-merged" in n for n in result.brief.sub_agent_notes)
    # Hand-merge still carries both halves verbatim from the specialist output.
    assert result.brief.inbound_markdown == _basic_inbound_half().markdown
    assert result.brief.outbound_markdown == _basic_outbound_half().markdown


def test_country_caveat_aggregator_injects_sci_his_for_dominant_fallback():
    """When > 30% of inbound lanes are sci_his, a caveat appears."""
    state = _golden_state()
    # Make all inbound lanes sci_his
    for c in state.corridor_metrics:
        if int(c.get("destination_m49") or -1) == 250:
            c["cvs_mode"] = "sci_his"

    inbound = _basic_inbound_half()
    outbound = _basic_outbound_half()
    synth = _basic_synth()
    synth.caveats = []  # no caveats supplied by synth
    provider = _MultiCallProvider(inbound=inbound, outbound=outbound, synthesised=synth)
    with patch.object(cb_mod, "get_provider", return_value=provider):
        result = cb_mod.generate_country_brief(250, state=state, verify="strict")
    assert any("sci_his" in c.lower() for c in result.brief.caveats), (
        f"expected sci_his caveat; got {result.brief.caveats}"
    )


def test_country_caveat_aggregator_injects_informational():
    """When >20% of inbound lanes are informational, a caveat appears."""
    state = _golden_state()
    inbound = _basic_inbound_half()
    outbound = _basic_outbound_half()
    synth = _basic_synth()
    synth.caveats = []
    provider = _MultiCallProvider(inbound=inbound, outbound=outbound, synthesised=synth)
    with patch.object(cb_mod, "get_provider", return_value=provider):
        result = cb_mod.generate_country_brief(250, state=state, verify="strict")
    # France's 2 inbound lanes: 1 confirmed, 1 informational → 50%
    assert any("informational" in c.lower() for c in result.brief.caveats), (
        f"expected informational caveat; got {result.brief.caveats}"
    )


def test_signal_dedup_in_synthesiser():
    """Identical (source_field, value) pairs collapse."""
    state = _golden_state()
    inbound = CountryHalf(
        markdown="In",
        signals=[CitedSignal(name="A", source_field="acep", value=0.62, band="med")],
    )
    outbound = CountryHalf(
        markdown="Out",
        signals=[CitedSignal(name="B", source_field="acep", value=0.62, band="med")],
    )
    # Synth duplicates them too.
    synth = CountryBrief(
        headline="H",
        inbound_markdown="In",
        outbound_markdown="Out",
        key_signals=[
            CitedSignal(name="A", source_field="acep", value=0.62, band="med"),
            CitedSignal(name="A2", source_field="acep", value=0.62, band="med"),  # dup
            CitedSignal(name="C", source_field="his", value=0.4, band="med"),
        ],
        confidence="med",
    )
    provider = _MultiCallProvider(inbound=inbound, outbound=outbound, synthesised=synth)
    with patch.object(cb_mod, "get_provider", return_value=provider):
        result = cb_mod.generate_country_brief(250, state=state, verify="off")
    # The duplicate (acep, 0.62) should collapse to one.
    keys = [(s.source_field, str(s.value)) for s in result.brief.key_signals]
    assert keys.count(("acep", "0.62")) == 1
