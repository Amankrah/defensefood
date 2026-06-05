"""
Conversational Q&A runner (Phase 4).

Two-stage pipeline:

1. **Routing** — a cheap Haiku call extracts intent + entities and decides
   whether the query is in scope. Out-of-scope queries short-circuit with a
   graceful refusal; no Sonnet tokens are spent.

2. **Composition** — a Sonnet tool-use loop with the full corpus toolbox.
   The agent plans and executes, then submits a structured ``QATurn`` via
   the forced ``submit_qa_answer`` tool. The tool trace itself is the
   audit-friendly "plan".

Conversation memory lives in SQLite (``conversations`` + ``messages``
tables). The runner reads the last few turns to give the composer
multi-turn context. Older context is summarised when the message count
crosses ``QA_SUMMARISE_AFTER`` so the prompt stays bounded.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from defensefood.agent import cache as agent_cache
from defensefood.agent.briefs.lane_brief import _sanitise_style
from defensefood.agent.config import ProviderName, Tier, get_config
from defensefood.agent.provider import AgentRun, get_provider
from defensefood.agent.qa.schemas import (
    IntentClassification,
    QATurn,
    QueryEntities,
)
from defensefood.agent.tools import TOOL_REGISTRY, tool

logger = logging.getLogger(__name__)

VerifyMode = Literal["strict", "fast", "off"]

# All corpus tools available to the composer. We deliberately offer the full
# toolbox so the model can choose the right shape per query.
_QA_COMPOSER_TOOLS: list[str] = [
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
    "compare_periods",
    "compare_corpus_periods",
    "detect_clusters",
    "get_data_coverage",
]

QA_HISTORY_WINDOW = 6  # most recent message pairs included verbatim
QA_SUMMARISE_AFTER = 14  # total turns after which older context is summarised


# ── forced-submit tools ──────────────────────────────────────────────────


@tool(
    name="submit_intent",
    description=(
        "Submit the routing classification. Call exactly once after deciding "
        "the intent + extracting entity hints."
    ),
)
def _submit_intent(args: IntentClassification, *, state: Any) -> dict[str, Any]:
    return args.model_dump()


@tool(
    name="submit_qa_answer",
    description=(
        "Submit the final Q&A answer. Call exactly once. answer_markdown is "
        "the user-facing narrative; key_signals carry every cited number; "
        "structured_data is optional and only used when the answer is "
        "naturally tabular."
    ),
)
def _submit_qa_answer(args: QATurn, *, state: Any) -> dict[str, Any]:
    return args.model_dump()


# ── prompt loaders ────────────────────────────────────────────────────────


def _load_prompt(name: str) -> str:
    cfg = get_config()
    backend_root = Path(__file__).resolve().parents[3]
    p = backend_root / cfg.prompts_dir / name
    if not p.exists():
        raise FileNotFoundError(f"QA prompt missing: {p}")
    return p.read_text(encoding="utf-8")


# ── conversation history ──────────────────────────────────────────────────


def _format_history_for_composer(
    history_msgs: Iterable[dict[str, Any]],
) -> str:
    """Compact, model-friendly transcript for the composer's user prompt."""
    lines: list[str] = []
    for m in history_msgs:
        role = m.get("role", "user")
        content = m.get("content")
        if role == "assistant" and isinstance(content, dict):
            text = content.get("answer_markdown") or ""
        elif isinstance(content, dict):
            text = content.get("query") or content.get("text") or str(content)
        else:
            text = str(content)
        if text:
            lines.append(f"{role}: {text.strip()}")
    return "\n\n".join(lines)


def _summarise_old_history(
    history_msgs: list[dict[str, Any]],
    *,
    provider: Optional[ProviderName],
) -> str:
    """Compact a long history into a single summary string.

    Returns "" if no compression is needed. Uses the route tier so the cost
    stays low.
    """
    if len(history_msgs) <= QA_HISTORY_WINDOW:
        return ""
    older = history_msgs[:-QA_HISTORY_WINDOW]
    if not older:
        return ""
    transcript = _format_history_for_composer(older)
    if not transcript:
        return ""
    prov = get_provider(provider)
    try:
        result = prov.tool_use_loop(
            system_prompt=(
                "You are summarising the older turns of a research Q&A so a "
                "downstream agent can carry context. Output 2 to 4 sentences "
                "capturing what the user has been asking about and what was "
                "answered. No em-dashes; analyst voice; no AI scaffolding."
            ),
            user_prompt=(
                "Summarise the conversation so far:\n\n" + transcript[:4000]
            ),
            tool_names=[],
            state=None,
            tier="route",
            max_iters=1,
            max_tokens=400,
            temperature=0.2,
        )
        return (result.final_text or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("History summarisation failed: %s", exc)
        return ""


# ── stage 1: routing ─────────────────────────────────────────────────────


def _classify_intent(
    query: str,
    *,
    provider: Optional[ProviderName],
) -> tuple[IntentClassification, AgentRun]:
    prov = get_provider(provider)
    system = _load_prompt("qa_intent.md")
    run = prov.tool_use_loop(
        system_prompt=system,
        user_prompt=f"User query:\n\n{query.strip()}",
        tool_names=["submit_intent"],
        state=None,
        tier="route",
        max_iters=2,
        max_tokens=600,
        temperature=0.0,
        force_tool="submit_intent",
    )
    if run.structured_output is None:
        # Last-ditch: assume in_scope, narrative_freeform, no entities.
        fallback = IntentClassification(
            intent="narrative_freeform",
            in_scope=True,
            entities=QueryEntities(),
        )
        return fallback, run
    try:
        return IntentClassification.model_validate(run.structured_output), run
    except ValidationError:
        return (
            IntentClassification(
                intent="narrative_freeform",
                in_scope=True,
                entities=QueryEntities(),
            ),
            run,
        )


# ── stage 2: composition ─────────────────────────────────────────────────


def _build_composer_user_prompt(
    query: str,
    classification: IntentClassification,
    summary: str,
    recent_transcript: str,
) -> str:
    import json as _json

    parts: list[str] = []
    parts.append("## Current question\n\n" + query.strip())
    parts.append(
        "## Intent (from routing)\n\n```json\n"
        + _json.dumps(classification.model_dump(), ensure_ascii=False, indent=2)
        + "\n```"
    )
    if summary:
        parts.append("## Earlier conversation (summary)\n\n" + summary)
    if recent_transcript:
        parts.append("## Recent conversation (verbatim)\n\n" + recent_transcript)
    parts.append(
        "Decide which tools to call, gather what you need, then call "
        "`submit_qa_answer` exactly once."
    )
    return "\n\n".join(parts)


def _compose(
    *,
    query: str,
    classification: IntentClassification,
    summary: str,
    recent_transcript: str,
    state: Any,
    provider: Optional[ProviderName],
    tier: Tier,
    max_iters: int,
) -> tuple[QATurn, AgentRun]:
    prov = get_provider(provider)
    system = _load_prompt("qa_compose.md")
    user_prompt = _build_composer_user_prompt(
        query, classification, summary, recent_transcript
    )
    run = prov.tool_use_loop(
        system_prompt=system,
        user_prompt=user_prompt,
        tool_names=_QA_COMPOSER_TOOLS + ["submit_qa_answer"],
        state=state,
        tier=tier,
        max_iters=max_iters,
        max_tokens=1800,
        temperature=0.3,
    )

    # Forced-submit fallback when the agent ends with prose.
    if run.structured_output is None:
        prior_text = (run.final_text or "").strip()
        force_user = (
            user_prompt
            + "\n\n"
            + "Your previous draft was the following text. Package it as a "
            + "single submit_qa_answer call.\n\n"
            + (prior_text or "(no prior text)")
        )
        forced = prov.tool_use_loop(
            system_prompt=system,
            user_prompt=force_user,
            tool_names=["submit_qa_answer"],
            state=state,
            tier=tier,
            max_iters=2,
            max_tokens=1500,
            temperature=0.2,
            force_tool="submit_qa_answer",
        )
        run.tokens_in += forced.tokens_in
        run.tokens_out += forced.tokens_out
        run.cost_usd += forced.cost_usd
        run.tool_traces.extend(forced.tool_traces)
        if forced.structured_output is None:
            raise RuntimeError(
                "Composer failed to call submit_qa_answer even under forced "
                "tool choice. Provider may be unhealthy."
            )
        run.structured_output = forced.structured_output

    try:
        turn = QATurn.model_validate(run.structured_output)
    except ValidationError as exc:
        raise RuntimeError(
            f"submit_qa_answer produced an invalid QATurn: {exc}"
        ) from exc
    return turn, run


# ── style sanitiser for QATurn ────────────────────────────────────────────


def _sanitise_turn_style(turn: QATurn) -> list[str]:
    """Apply the shared style sanitiser across answer + caveats."""
    notes: list[str] = []
    new_ans, ans_notes = _sanitise_style(turn.answer_markdown)
    turn.answer_markdown = new_ans
    notes.extend(ans_notes)
    new_caveats: list[str] = []
    for c in turn.caveats:
        nc, cn = _sanitise_style(c)
        new_caveats.append(nc)
        notes.extend(cn)
    turn.caveats = new_caveats
    if turn.structured_data is not None and turn.structured_data.title:
        new_title, t_notes = _sanitise_style(turn.structured_data.title)
        turn.structured_data.title = new_title
        notes.extend(t_notes)
    return notes


# ── public entry point ──────────────────────────────────────────────────


class QAResult(BaseModel):
    conversation_id: str
    turn: QATurn
    classification: IntentClassification
    refused: bool = False
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)


def _refusal_turn(reason: str) -> QATurn:
    return QATurn(
        answer_markdown=(
            f"This corpus cannot answer that. {reason}\n\n"
            "Try asking about specific corridors (commodity + origin + "
            "destination), country exposure, period-over-period shifts, or "
            "metric methodology."
        ),
        key_signals=[],
        structured_data=None,
        caveats=[],
        confidence="med",
    )


def handle_query(
    query: str,
    *,
    state: Any,
    conversation_id: Optional[str] = None,
    provider: Optional[ProviderName] = None,
    tier: Tier = "narrative",
    max_iters: int = 5,
    verify: VerifyMode = "fast",
) -> QAResult:
    """Run one Q&A turn end to end.

    1. Route the query (Haiku).
    2. If out-of-scope, persist the refusal and return.
    3. Otherwise compose (Sonnet) with conversation memory.
    4. Sanitise the answer and persist the turn.
    """
    if not query or not query.strip():
        raise ValueError("Empty query.")

    t0 = time.perf_counter()
    convo_id = conversation_id or uuid.uuid4().hex
    agent_cache.upsert_conversation(convo_id)

    # Persist the user turn first so audit ordering is honest even if anything
    # downstream crashes.
    agent_cache.append_message(
        conversation_id=convo_id,
        role="user",
        content={"query": query.strip()},
    )

    classification, intent_run = _classify_intent(query, provider=provider)

    # Out-of-scope short-circuit.
    if not classification.in_scope or classification.intent == "out_of_scope":
        reason = classification.refusal_reason or (
            "It is outside the EU food fraud vulnerability corpus."
        )
        turn = _refusal_turn(reason)
        agent_cache.append_message(
            conversation_id=convo_id,
            role="assistant",
            content=turn.model_dump(),
            tokens_in=intent_run.tokens_in,
            tokens_out=intent_run.tokens_out,
            cost_usd=intent_run.cost_usd,
        )
        return QAResult(
            conversation_id=convo_id,
            turn=turn,
            classification=classification,
            refused=True,
            provider=intent_run.provider,
            model=intent_run.model,
            tokens_in=intent_run.tokens_in,
            tokens_out=intent_run.tokens_out,
            cost_usd=intent_run.cost_usd,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            tool_trace=[],
        )

    # Conversation memory.
    convo = agent_cache.get_conversation(convo_id)
    messages = (convo or {}).get("messages") or []
    # Exclude the user message we just stored.
    history = messages[:-1] if messages else []
    summary = _summarise_old_history(history, provider=provider)
    recent_window = history[-QA_HISTORY_WINDOW:] if history else []
    recent_transcript = _format_history_for_composer(recent_window)

    # Composition.
    turn, compose_run = _compose(
        query=query,
        classification=classification,
        summary=summary,
        recent_transcript=recent_transcript,
        state=state,
        provider=provider,
        tier=tier,
        max_iters=max_iters,
    )

    if verify != "off":
        turn.verifier_notes = _sanitise_turn_style(turn)

    # Persist the assistant turn with merged token accounting.
    total_tokens_in = intent_run.tokens_in + compose_run.tokens_in
    total_tokens_out = intent_run.tokens_out + compose_run.tokens_out
    total_cost = intent_run.cost_usd + compose_run.cost_usd

    agent_cache.append_message(
        conversation_id=convo_id,
        role="assistant",
        content=turn.model_dump(),
        tool_calls=[
            {"name": t.name, "args": t.args, "latency_ms": t.latency_ms}
            for t in compose_run.tool_traces
        ],
        tokens_in=total_tokens_in,
        tokens_out=total_tokens_out,
        cost_usd=total_cost,
    )

    return QAResult(
        conversation_id=convo_id,
        turn=turn,
        classification=classification,
        refused=False,
        provider=compose_run.provider,
        model=compose_run.model,
        tokens_in=total_tokens_in,
        tokens_out=total_tokens_out,
        cost_usd=total_cost,
        latency_ms=int((time.perf_counter() - t0) * 1000),
        tool_trace=[
            {
                "name": t.name,
                "args": t.args,
                "result": t.result,
                "latency_ms": t.latency_ms,
            }
            for t in compose_run.tool_traces
        ],
    )


__all__ = [
    "QAResult",
    "VerifyMode",
    "handle_query",
]
