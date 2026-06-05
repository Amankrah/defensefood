"""Phase 4 — conversational Q&A runner, mocked providers."""

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


from defensefood.agent.qa import runner as qa_runner
from defensefood.agent.qa.schemas import (
    IntentClassification,
    QATurn,
    QueryEntities,
)
from defensefood.agent.provider import AgentRun
from defensefood.agent import cache as agent_cache


def _basic_state() -> SimpleNamespace:
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
                "notification_count": 7,
                "cvs_mode": "sci_crs_his",
                "market_presence": "confirmed",
                "provenance": "faostat",
            },
        ],
        coverage={"corridors_total": 1},
        dependency_history={},
    )


# ── mock providers ───────────────────────────────────────────────────────


class _ScriptedQAProvider:
    """Mock provider that returns scripted IntentClassification and QATurn.

    The runner makes (at minimum) two tool_use_loop calls per turn:
        1. classification (force_tool='submit_intent', tier='route')
        2. composer (allows all tools, may invoke submit_qa_answer)

    This mock identifies which stage by inspecting force_tool / tool_names.
    """

    name = "anthropic"

    def __init__(
        self,
        *,
        intent: IntentClassification,
        turn: Optional[QATurn] = None,
        intent_cost: float = 0.0005,
        turn_cost: float = 0.012,
    ) -> None:
        self._intent = intent
        self._turn = turn
        self._intent_cost = intent_cost
        self._turn_cost = turn_cost
        self.calls: list[dict] = []

    def tool_use_loop(self, *, force_tool: Optional[str] = None, **kw) -> AgentRun:
        self.calls.append(
            {"force": force_tool, "tools": kw.get("tool_names"), "tier": kw.get("tier")}
        )
        if force_tool == "submit_intent" or (
            kw.get("tool_names") and "submit_intent" in (kw.get("tool_names") or [])
        ):
            return AgentRun(
                final_text="",
                tool_traces=[],
                messages=[],
                tokens_in=300,
                tokens_out=100,
                cost_usd=self._intent_cost,
                model="claude-haiku-4-5-20251001",
                provider="anthropic",
                stop_reason="tool_use",
                structured_output=self._intent.model_dump(),
            )
        # Composer branch.
        if self._turn is None:
            return AgentRun(
                final_text="(no turn provided)",
                tool_traces=[],
                messages=[],
                tokens_in=2000,
                tokens_out=400,
                cost_usd=self._turn_cost,
                model="claude-sonnet-4-6",
                provider="anthropic",
                stop_reason="end_turn",
                structured_output=None,
            )
        return AgentRun(
            final_text="",
            tool_traces=[],
            messages=[],
            tokens_in=2000,
            tokens_out=400,
            cost_usd=self._turn_cost,
            model="claude-sonnet-4-6",
            provider="anthropic",
            stop_reason="tool_use",
            structured_output=self._turn.model_dump(),
        )


def _basic_intent(in_scope: bool = True, intent: str = "lookup") -> IntentClassification:
    return IntentClassification(
        intent=intent,  # type: ignore[arg-type]
        in_scope=in_scope,
        refusal_reason=None if in_scope else "Outside the corpus.",
        entities=QueryEntities(),
    )


def _basic_turn() -> QATurn:
    from defensefood.agent.briefs.schemas import CitedSignal
    return QATurn(
        answer_markdown=(
            "Spain mussels into France carry a Composite Vulnerability Score (CVS) "
            "of 0.345, in the watchlist band."
        ),
        key_signals=[CitedSignal(name="CVS", source_field="cvs", value=0.345, band="med")],
        structured_data=None,
        caveats=[],
        confidence="med",
    )


# ── tests ────────────────────────────────────────────────────────────────


def test_out_of_scope_query_short_circuits_without_composer_call():
    """When intent classifier marks the query out_of_scope, no composer
    (Sonnet) call should be made. The user gets a graceful refusal."""
    state = _basic_state()
    prov = _ScriptedQAProvider(
        intent=_basic_intent(in_scope=False, intent="out_of_scope"),
        turn=None,
    )
    with patch.object(qa_runner, "get_provider", return_value=prov):
        result = qa_runner.handle_query("What is the weather in Madrid?", state=state)

    assert result.refused is True
    assert "corpus cannot answer" in result.turn.answer_markdown.lower() or (
        "outside" in result.turn.answer_markdown.lower()
    )
    # Only the intent classification call ran. No composer call.
    assert len(prov.calls) == 1
    assert prov.calls[0]["tier"] == "route"


def test_in_scope_query_runs_full_pipeline_and_persists_turn():
    """In-scope queries: classify → compose → persist to messages."""
    state = _basic_state()
    prov = _ScriptedQAProvider(
        intent=_basic_intent(in_scope=True, intent="lookup"),
        turn=_basic_turn(),
    )
    with patch.object(qa_runner, "get_provider", return_value=prov):
        result = qa_runner.handle_query(
            "What is CVS for Spain mussels into France?",
            state=state,
        )

    assert result.refused is False
    assert result.turn.answer_markdown.startswith("Spain mussels into France")
    # Two LLM calls: classify + compose.
    assert len(prov.calls) == 2
    # Convo + 2 messages (user + assistant) persisted.
    convo = agent_cache.get_conversation(result.conversation_id)
    assert convo is not None
    assert len(convo["messages"]) == 2
    assert convo["messages"][0]["role"] == "user"
    assert convo["messages"][1]["role"] == "assistant"


def test_conversation_id_is_generated_when_not_supplied():
    state = _basic_state()
    prov = _ScriptedQAProvider(intent=_basic_intent(), turn=_basic_turn())
    with patch.object(qa_runner, "get_provider", return_value=prov):
        r = qa_runner.handle_query("hello", state=state)
    assert r.conversation_id
    assert len(r.conversation_id) >= 16


def test_conversation_id_is_reused_across_turns():
    """Two turns with the same conversation_id append to the same row set."""
    state = _basic_state()
    prov = _ScriptedQAProvider(intent=_basic_intent(), turn=_basic_turn())
    with patch.object(qa_runner, "get_provider", return_value=prov):
        first = qa_runner.handle_query("first?", state=state)
        second = qa_runner.handle_query(
            "second?",
            state=state,
            conversation_id=first.conversation_id,
        )
    assert second.conversation_id == first.conversation_id
    convo = agent_cache.get_conversation(first.conversation_id)
    assert convo is not None
    # 2 turns × (user + assistant) = 4 messages.
    assert len(convo["messages"]) == 4
    assert [m["role"] for m in convo["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_empty_query_raises():
    state = _basic_state()
    prov = _ScriptedQAProvider(intent=_basic_intent(), turn=_basic_turn())
    with patch.object(qa_runner, "get_provider", return_value=prov):
        with pytest.raises(ValueError, match="Empty query"):
            qa_runner.handle_query("   ", state=state)


def test_force_tool_fallback_when_composer_returns_text():
    """If the composer ends with text, the runner forces submit_qa_answer."""

    class _TextThenForced:
        name = "anthropic"

        def __init__(self, intent: IntentClassification, turn: QATurn) -> None:
            self._intent = intent
            self._turn = turn
            self.calls: list[dict] = []

        def tool_use_loop(self, *, force_tool=None, **kw) -> AgentRun:
            self.calls.append({"force": force_tool, "tools": kw.get("tool_names")})
            tool_names = kw.get("tool_names") or []
            if "submit_intent" in tool_names:
                return AgentRun(
                    final_text="",
                    tool_traces=[],
                    messages=[],
                    tokens_in=300,
                    tokens_out=100,
                    cost_usd=0.0005,
                    model="claude-haiku-4-5-20251001",
                    provider="anthropic",
                    stop_reason="tool_use",
                    structured_output=self._intent.model_dump(),
                )
            if force_tool == "submit_qa_answer":
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
                    structured_output=self._turn.model_dump(),
                )
            return AgentRun(
                final_text="Some thinking but no submit.",
                tool_traces=[],
                messages=[],
                tokens_in=2000,
                tokens_out=400,
                cost_usd=0.012,
                model="claude-sonnet-4-6",
                provider="anthropic",
                stop_reason="end_turn",
                structured_output=None,
            )

    state = _basic_state()
    prov = _TextThenForced(_basic_intent(), _basic_turn())
    with patch.object(qa_runner, "get_provider", return_value=prov):
        r = qa_runner.handle_query("anything", state=state)
    assert r.refused is False
    # 3 calls: classify + composer (no submit) + forced composer.
    assert len(prov.calls) == 3
    assert prov.calls[2]["force"] == "submit_qa_answer"


def test_style_sanitiser_strips_em_dashes_from_answer():
    state = _basic_state()
    dirty = QATurn(
        answer_markdown=(
            "Spain mussels into France — strongest hazard lane. CVS is 0.345."
        ),
        key_signals=[],
        structured_data=None,
        caveats=[],
        confidence="med",
    )
    prov = _ScriptedQAProvider(intent=_basic_intent(), turn=dirty)
    with patch.object(qa_runner, "get_provider", return_value=prov):
        r = qa_runner.handle_query("explain", state=state)
    assert "—" not in r.turn.answer_markdown


def test_qa_endpoint_returns_structured_response():
    """Smoke: POST /api/v1/agent/qa returns a QAResultResponse-shaped dict."""
    from fastapi.testclient import TestClient
    from defensefood.api.main import app
    import defensefood.api.dependencies as deps

    deps._state = None
    state = _basic_state()
    from defensefood.models.scores import ScoringConfig
    state.scoring_config = ScoringConfig()
    state.trade_period = 2023
    app.dependency_overrides[deps.get_state] = lambda: state

    prov = _ScriptedQAProvider(intent=_basic_intent(), turn=_basic_turn())
    client = TestClient(app)
    with patch.object(qa_runner, "get_provider", return_value=prov):
        r = client.post(
            "/api/v1/agent/qa",
            json={"query": "what is CVS for Spain mussels into France?"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["refused"] is False
    assert body["turn"]["answer_markdown"].startswith("Spain mussels")
    assert body["conversation_id"]
    app.dependency_overrides.clear()


def test_get_conversation_endpoint_returns_persisted_history():
    """GET /api/v1/agent/conversations/{id} returns the full message list."""
    from fastapi.testclient import TestClient
    from defensefood.api.main import app
    import defensefood.api.dependencies as deps

    deps._state = None
    state = _basic_state()
    from defensefood.models.scores import ScoringConfig
    state.scoring_config = ScoringConfig()
    state.trade_period = 2023
    app.dependency_overrides[deps.get_state] = lambda: state

    prov = _ScriptedQAProvider(intent=_basic_intent(), turn=_basic_turn())
    client = TestClient(app)
    with patch.object(qa_runner, "get_provider", return_value=prov):
        r1 = client.post(
            "/api/v1/agent/qa",
            json={"query": "first question"},
        )
    convo_id = r1.json()["conversation_id"]

    r2 = client.get(f"/api/v1/agent/conversations/{convo_id}")
    assert r2.status_code == 200
    convo = r2.json()
    assert convo["id"] == convo_id
    # User + assistant.
    assert len(convo["messages"]) == 2

    app.dependency_overrides.clear()
