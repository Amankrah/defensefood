"""Phase 3 — period shift diagnostic, mocked provider, golden fixture state."""

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


from defensefood.agent.briefs import period_shift as ps_mod
from defensefood.agent.briefs.schemas import (
    CitedSignal,
    PeriodCluster,
    PeriodMover,
    PeriodShiftBrief,
)
from defensefood.agent.provider import AgentRun


def _two_period_state() -> SimpleNamespace:
    """Build a fixture state with two corridors and two periods of coverage.

    The shape mirrors the real pipeline: corridor records have NO
    'trade_periods' field. Per-period dependency snapshots live on
    state.dependency_history. state.coverage carries the corpus-wide period
    list.
    """
    corridors = [
        {
            "commodity_hs": "30771",
            "commodity_name": "Mussels, frozen",
            "destination_m49": 250,
            "destination_country": "France",
            "origin_m49": 724,
            "origin_country": "Spain",
            "cvs": 0.345,
            "cvs_mode": "sci_crs_his",
            "his": 0.42,
            "market_presence": "confirmed",
            "provenance": "faostat",
            "notification_count": 7,
        },
        {
            "commodity_hs": "100630",
            "commodity_name": "Semi-milled rice",
            "destination_m49": 250,
            "destination_country": "France",
            "origin_m49": 380,
            "origin_country": "Italy",
            "cvs": 0.18,
            "cvs_mode": "sci_his",
            "his": 0.12,
            "market_presence": "informational",
            "provenance": "trade_only",
            "notification_count": 2,
        },
    ]
    # dependency_history: keyed by period -> {key -> entry}
    history = {
        2022: {
            ("30771", 250, 724): {
                "cvs": 0.28,
                "bdi": 0.55,
                "ocs": 0.45,
                "hhi": 0.38,
                "idr": 0.7,
                "sci": 1.0,
                "his": 0.40,
                "notification_count": 4,
            },
            ("100630", 250, 380): {
                "cvs": 0.20,
                "bdi": 0.30,
                "ocs": 0.50,
                "hhi": 0.40,
                "idr": 0.6,
                "sci": 0.8,
                "his": 0.10,
                "notification_count": 1,
            },
        },
        2023: {
            ("30771", 250, 724): {
                "cvs": 0.345,
                "bdi": 0.60,
                "ocs": 0.50,
                "hhi": 0.40,
                "idr": 0.7,
                "sci": 1.1,
                "his": 0.42,
                "notification_count": 7,
            },
            ("100630", 250, 380): {
                "cvs": 0.18,
                "bdi": 0.28,
                "ocs": 0.48,
                "hhi": 0.39,
                "idr": 0.6,
                "sci": 0.8,
                "his": 0.12,
                "notification_count": 2,
            },
        },
    }
    return SimpleNamespace(
        corridor_metrics=corridors,
        dependency_history=history,
        notifications_by_corridor={},
        coverage={"corridors_total": 2},
    )


def _basic_brief() -> PeriodShiftBrief:
    return PeriodShiftBrief(
        headline="Between 2022 and 2023, 1 corridor rose and 1 stayed stable.",
        body_markdown=(
            "Across 2 corridors with multi-year coverage, the median Composite "
            "Vulnerability Score (CVS) movement was small. Spain mussels into "
            "France rose by 0.065 CVS while Italian rice into France was flat."
        ),
        period_a=2022,
        period_b=2023,
        top_risers=[
            PeriodMover(
                lane_key="30771/250/724",
                label="Spain mussels into France",
                cvs_a=0.28,
                cvs_b=0.345,
                cvs_delta=0.065,
                notif_delta=3,
                direction="rising",
                explanation="CVS rose from 0.28 to 0.345 as alerts grew from 4 to 7.",
            ),
        ],
        top_fallers=[],
        emerging_clusters=[],
        key_signals=[
            CitedSignal(
                name="Corridors compared",
                source_field="corpus_corridors_compared",
                value=2,
                band="unknown",
            ),
            CitedSignal(
                name="Risers",
                source_field="corpus_risers",
                value=1,
                band="unknown",
            ),
        ],
        caveats=[],
        confidence="med",
    )


class _MockProvider:
    """Mock provider that returns a fixed PeriodShiftBrief."""

    name = "anthropic"

    def __init__(
        self,
        *,
        brief: PeriodShiftBrief,
        cost_usd: float = 0.008,
        tokens_in: int = 1200,
        tokens_out: int = 350,
    ) -> None:
        self._brief = brief
        self._cost = cost_usd
        self._tin = tokens_in
        self._tout = tokens_out
        self.calls: list[dict] = []

    def tool_use_loop(self, *, force_tool: Optional[str] = None, **kw) -> AgentRun:
        self.calls.append(
            {
                "user": kw.get("user_prompt"),
                "tools": kw.get("tool_names"),
                "force": force_tool,
            }
        )
        return AgentRun(
            final_text="",
            tool_traces=[],
            messages=[],
            tokens_in=self._tin,
            tokens_out=self._tout,
            cost_usd=self._cost,
            model="claude-sonnet-4-6",
            provider="anthropic",
            stop_reason="tool_use",
            structured_output=self._brief.model_dump(),
        )


# ── tests ────────────────────────────────────────────────────────────────


def test_period_resolution_picks_latest_two_when_unspecified():
    state = _two_period_state()
    mock = _MockProvider(brief=_basic_brief())
    with patch.object(ps_mod, "get_provider", return_value=mock):
        result = ps_mod.generate_period_shift_brief(state=state, verify="off")
    assert result.period_a == 2022
    assert result.period_b == 2023


def test_compare_corpus_periods_uses_dependency_history_not_corridor_trade_periods():
    """Regression: previously the tool checked corridor.trade_periods which is
    never set on individual corridor records (it lives on state.coverage).
    The tool must read state.dependency_history directly.
    """
    from defensefood.agent.tools import invoke_tool

    state = _two_period_state()
    # Confirm: per-corridor 'trade_periods' is NOT a field that exists.
    for c in state.corridor_metrics:
        assert c.get("trade_periods") is None or "trade_periods" not in c, (
            "Test premise: per-corridor trade_periods does not exist on records "
            "loaded by the dependencies pipeline. If this changes, the regression "
            "test below must be updated."
        )
    # Tool must still find both corridors comparable, because dependency_history
    # has snapshots for both 2022 and 2023.
    result = invoke_tool(
        "compare_corpus_periods",
        {"period_a": 2022, "period_b": 2023, "top_n": 10},
        state=state,
    )
    assert result["ok"], result
    totals = result["result"]["totals"]
    assert totals["corridors_compared"] == 2
    assert totals["corridors_in_a_only"] == 0
    assert totals["corridors_in_b_only"] == 0
    assert 2022 in totals["available_periods"] and 2023 in totals["available_periods"]


def test_resolve_periods_defaults_to_widest_window_not_latest_pair():
    """When 6 years of dependency snapshots are populated, the default should
    span (earliest, latest), not just (latest-1, latest)."""
    state = _two_period_state()
    # Synthesise 6 periods, copying the 2023 snapshot into each. The values
    # are irrelevant for the resolver test; only the year set matters.
    base = state.dependency_history[2023]
    state.dependency_history = {y: base for y in (2018, 2019, 2020, 2021, 2022, 2023)}
    pa, pb = ps_mod._resolve_periods(state, None, None)
    assert pa == 2018
    assert pb == 2023


def test_per_period_notification_counts_come_from_notifications_by_corridor():
    """compare_corpus_periods must count notifications per year from
    state.notifications_by_corridor, NOT from the dependency snapshot
    (which only carries Section 2 structural metrics)."""
    from defensefood.agent.tools import invoke_tool

    state = _two_period_state()
    # Attach notifications: 2 in 2022, 5 in 2023 on the mussels lane.
    lane_key = ("30771", 250, 724)
    state.notifications_by_corridor = {
        lane_key: (
            [{"period": 202205} for _ in range(2)]
            + [{"period": 202311} for _ in range(5)]
        ),
    }
    result = invoke_tool(
        "compare_corpus_periods",
        {"period_a": 2022, "period_b": 2023, "top_n": 10},
        state=state,
    )
    assert result["ok"], result
    movers = result["result"]["top_movers"]
    mussels = next(m for m in movers if m["commodity_hs"] == "30771")
    assert mussels["notif_a"] == 2
    assert mussels["notif_b"] == 5
    assert mussels["notif_delta"] == 3


def test_resolve_periods_falls_back_when_only_one_period_populated():
    """If dependency_history only has one period of snapshots, default to that
    period and the one before it.
    """
    state = _two_period_state()
    # Wipe 2022 → only 2023 populated.
    state.dependency_history = {2023: state.dependency_history[2023]}
    pa, pb = ps_mod._resolve_periods(state, None, None)
    assert pa == 2022
    assert pb == 2023


def test_better_error_message_when_no_overlap_suggests_alternative_pair():
    """When the requested period_a is empty, the error should suggest the
    closest viable pair from available_periods.
    """
    state = _two_period_state()
    mock = _MockProvider(brief=_basic_brief())
    with patch.object(ps_mod, "get_provider", return_value=mock):
        with pytest.raises(ValueError) as ei:
            # 2024 isn't in dependency_history at all.
            ps_mod.generate_period_shift_brief(
                state=state, period_a=2024, period_b=2023, verify="off"
            )
    msg = str(ei.value)
    assert "Available dependency periods" in msg
    assert "Try ?period_a=" in msg


def test_preload_block_embedded_in_user_prompt():
    """The corpus comparison + clusters are pre-loaded so the agent does not
    have to call those tools itself."""
    state = _two_period_state()
    mock = _MockProvider(brief=_basic_brief())
    with patch.object(ps_mod, "get_provider", return_value=mock):
        ps_mod.generate_period_shift_brief(state=state, verify="off")
    assert len(mock.calls) == 1
    up = mock.calls[0]["user"]
    assert "Pre-loaded data" in up
    assert '"compare_corpus_periods"' in up
    assert '"detect_clusters"' in up
    # Available optional tools, but NOT the compare tool again.
    offered = mock.calls[0]["tools"]
    assert "compare_corpus_periods" not in offered
    assert "detect_clusters" not in offered
    assert "submit_period_shift_brief" in offered


def test_no_overlap_raises():
    """If no corridors have coverage in both periods, the generator refuses."""
    state = _two_period_state()
    # Wipe the 2022 snapshots so no corridor has both periods of dependency data.
    state.dependency_history = {2023: state.dependency_history[2023]}
    mock = _MockProvider(brief=_basic_brief())
    with patch.object(ps_mod, "get_provider", return_value=mock):
        # Explicit period_a=2022 + period_b=2023 → no overlap because we only
        # have 2023 snapshots. Use explicit to avoid the resolver collapsing
        # back to a single-period default.
        with pytest.raises(ValueError, match="cannot synthesise|coverage"):
            ps_mod.generate_period_shift_brief(
                state=state, period_a=2022, period_b=2023, verify="off"
            )


def test_required_caveat_data_lag_always_injected():
    """The 'data lags by 1 to 2 years' caveat appears even when the brief omits it."""
    state = _two_period_state()
    mock = _MockProvider(brief=_basic_brief())
    with patch.object(ps_mod, "get_provider", return_value=mock):
        result = ps_mod.generate_period_shift_brief(state=state, verify="fast")
    joined = "\n".join(result.brief.caveats).lower()
    assert "lag" in joined or "through 2023" in joined or "field activity" in joined


def test_small_population_caveat_injected_when_under_100():
    """The small_population caveat appears for the 2-corridor fixture."""
    state = _two_period_state()
    mock = _MockProvider(brief=_basic_brief())
    with patch.object(ps_mod, "get_provider", return_value=mock):
        result = ps_mod.generate_period_shift_brief(state=state, verify="fast")
    joined = "\n".join(result.brief.caveats).lower()
    assert "small comparable population" in joined or "multi-year coverage" in joined


def test_style_sanitiser_strips_em_dashes_from_explanations():
    """Em-dashes in mover.explanation get cleaned during the verify pass."""
    state = _two_period_state()
    dirty_brief = _basic_brief()
    dirty_brief.top_risers[0].explanation = (
        "CVS rose from 0.28 to 0.345 — driven by alert growth."
    )
    mock = _MockProvider(brief=dirty_brief)
    with patch.object(ps_mod, "get_provider", return_value=mock):
        result = ps_mod.generate_period_shift_brief(state=state, verify="fast")
    assert "—" not in result.brief.top_risers[0].explanation


def test_force_tool_fallback_recovers_when_first_pass_returns_text():
    """If first pass ends without structured output, force-tool retry submits."""

    class _TextThenForced:
        name = "anthropic"

        def __init__(self, brief: PeriodShiftBrief) -> None:
            self._brief = brief
            self.calls: list[dict] = []

        def tool_use_loop(self, *, force_tool=None, **kw) -> AgentRun:
            self.calls.append({"force": force_tool})
            if force_tool == "submit_period_shift_brief":
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
            return AgentRun(
                final_text="I would describe the period shift as follows...",
                tool_traces=[],
                messages=[],
                tokens_in=1200,
                tokens_out=300,
                cost_usd=0.008,
                model="claude-sonnet-4-6",
                provider="anthropic",
                stop_reason="end_turn",
                structured_output=None,
            )

    state = _two_period_state()
    prov = _TextThenForced(_basic_brief())
    with patch.object(ps_mod, "get_provider", return_value=prov):
        result = ps_mod.generate_period_shift_brief(state=state, verify="off")
    assert len(prov.calls) == 2
    assert prov.calls[0]["force"] is None
    assert prov.calls[1]["force"] == "submit_period_shift_brief"
    assert result.brief.headline.startswith("Between 2022 and 2023")


# ── endpoint smoke ────────────────────────────────────────────────────────


def test_only_cached_returns_needs_generation_without_provider():
    """The only_cached probe must never invoke the provider when no cache exists."""
    from fastapi.testclient import TestClient
    from defensefood.api.main import app
    import defensefood.api.dependencies as deps

    deps._state = None
    state = _two_period_state()
    from defensefood.models.scores import ScoringConfig
    state.scoring_config = ScoringConfig()
    state.trade_period = 2023

    app.dependency_overrides[deps.get_state] = lambda: state

    def _explode(*a, **k):  # noqa: ARG001
        raise AssertionError("provider invoked on only_cached probe")

    client = TestClient(app)
    with patch.object(ps_mod, "get_provider", side_effect=_explode):
        r = client.get("/api/v1/agent/period-shift?only_cached=true&verify=off")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cache_hit"] is False
    assert body["needs_generation"] is True
    assert body["period_a"] == 2022
    assert body["period_b"] == 2023
    app.dependency_overrides.clear()
