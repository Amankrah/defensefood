"""
Agent endpoints — Phase 1 surface.

Currently exposes one route, ``GET /api/v1/agent/lane-brief/{hs}/{dest}/{origin}``,
which serves a generated lane forensic brief. Cached briefs are reused until
the corpus snapshot changes; SSE streaming is enabled with ``?stream=true``.

Later phases add ``/country-brief``, ``/period-shift``, ``/qa``, etc.
"""

from __future__ import annotations

import json
import logging
import time
from typing import AsyncIterator, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from defensefood.agent import cache as agent_cache
from defensefood.agent.briefs.country_brief import (
    CountryBriefResult,
    generate_country_brief,
)
from defensefood.agent.briefs.lane_brief import (
    LaneBriefResult,
    VerifyMode,
    generate_lane_brief,
)
from defensefood.agent.briefs.period_shift import (
    PeriodShiftResult,
    generate_period_shift_brief,
)
from defensefood.agent.briefs.hypotheses import (
    HypothesisResult,
    generate_hypotheses,
)
from defensefood.agent.briefs.anomaly_explainer import (
    AnomalyResult,
    generate_anomaly_explanation,
)
from defensefood.agent.qa import handle_query
from defensefood.agent.qa.runner import QAResult
from defensefood.api.dependencies import AppState, get_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


def _state_snapshot_hash(state: AppState) -> str:
    """Stable hash over (corpus size, scoring config, current trade year).

    Used as a cache key so a brief is reused only when the engine's outputs
    are identical to the moment the brief was first computed.
    """
    return agent_cache.snapshot_hash(
        [
            len(state.corridor_metrics),
            state.scoring_config.model_dump_json(),
            getattr(state, "trade_period", None),
        ]
    )


def _sse(event: str, payload: dict) -> bytes:
    """Format one Server-Sent Event."""
    return (
        f"event: {event}\n"
        f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
    ).encode("utf-8")


def _result_to_dict(result: LaneBriefResult) -> dict:
    """Pydantic v2 dumps Literal types fine; this is a thin wrapper for clarity."""
    return result.model_dump(mode="json")


# ── lane brief ─────────────────────────────────────────────────────────────


@router.get("/lane-brief/{commodity_hs}/{destination_m49}/{origin_m49}")
def lane_brief(
    commodity_hs: str,
    destination_m49: int,
    origin_m49: int,
    stream: bool = Query(
        False,
        description="Stream tool-call + final-brief events as Server-Sent Events.",
    ),
    verify: Literal["strict", "fast", "off"] = Query(
        "strict",
        description=(
            "Reflection mode. strict = re-fetch all cited signals and re-run on "
            "mismatch. fast = re-fetch but only annotate. off = skip."
        ),
    ),
    refresh: bool = Query(
        False,
        description="When true, bypass the cache and regenerate the brief.",
    ),
    only_cached: bool = Query(
        False,
        description=(
            "When true, return the cached brief if present without invoking the "
            "LLM. If no cache hit, return {cache_hit: false, needs_generation: true} "
            "with HTTP 200. Use for opt-in UX where new generation should be "
            "gated behind an explicit user action."
        ),
    ),
    state: AppState = Depends(get_state),
):
    """Generate (or return cached) lane forensic brief.

    Cache key: ``(use_case='lane_brief', target_key='hs/dest/origin', snapshot_hash)``.
    """
    target_key = f"{commodity_hs}/{destination_m49}/{origin_m49}"
    snap = _state_snapshot_hash(state)

    cached = (
        None if refresh
        else agent_cache.get_cached_brief("lane_brief", target_key, snap)
    )

    # Opt-in path: caller wants a cache-only probe with zero LLM cost.
    if only_cached:
        if cached:
            return {
                **cached["brief"],
                "cache_hit": True,
                "model": cached["model"],
                "provider": cached["provider"],
                "cost_usd": cached["cost_usd"],
                "latency_ms": cached["latency_ms"],
            }
        return {
            "cache_hit": False,
            "needs_generation": True,
            "target_key": target_key,
            "snapshot_hash": snap,
        }

    if cached and not stream:
        # Re-shape to match LaneBriefResult dict.
        return {
            **cached["brief"],
            "cache_hit": True,
            "model": cached["model"],
            "provider": cached["provider"],
            "cost_usd": cached["cost_usd"],
            "latency_ms": cached["latency_ms"],
        }

    if not stream:
        try:
            result = generate_lane_brief(
                commodity_hs,
                destination_m49,
                origin_m49,
                state=state,
                verify=verify,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        brief_id = agent_cache.store_brief(
            use_case="lane_brief",
            target_key=target_key,
            snapshot_hash=snap,
            brief=_result_to_dict(result),
            model=result.model,
            provider=result.provider,
            cost_usd=result.cost_usd,
            latency_ms=result.latency_ms,
        )
        agent_cache.append_audit(
            use_case="lane_brief",
            target_key=target_key,
            role="assistant",
            content={"brief": result.brief.model_dump(), "tool_trace": result.tool_trace},
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            brief_id=brief_id,
        )
        agent_cache.record_cost(
            use_case="lane_brief",
            provider=result.provider,
            model=result.model,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            usd=result.cost_usd,
        )
        return _result_to_dict(result)

    # Streaming branch.
    async def event_stream() -> AsyncIterator[bytes]:
        yield _sse(
            "status",
            {"phase": "starting", "target_key": target_key, "snapshot": snap},
        )

        if cached:
            yield _sse("final_brief", cached["brief"] | {"cache_hit": True})
            return

        try:
            result = generate_lane_brief(
                commodity_hs,
                destination_m49,
                origin_m49,
                state=state,
                verify=verify,
            )
        except ValueError as exc:
            yield _sse("error", {"message": str(exc), "code": 404})
            return
        except RuntimeError as exc:
            yield _sse("error", {"message": str(exc), "code": 502})
            return

        # Replay tool trace to the client so the UI can show "consulted X tools".
        for t in result.tool_trace:
            yield _sse(
                "tool_call",
                {"name": t["name"], "args": t["args"], "latency_ms": t["latency_ms"]},
            )
            yield _sse("tool_result", {"name": t["name"], "result": t["result"]})

        for note in result.brief.verifier_notes:
            yield _sse("verifier_note", {"note": note})

        brief_id = agent_cache.store_brief(
            use_case="lane_brief",
            target_key=target_key,
            snapshot_hash=snap,
            brief=_result_to_dict(result),
            model=result.model,
            provider=result.provider,
            cost_usd=result.cost_usd,
            latency_ms=result.latency_ms,
        )
        agent_cache.append_audit(
            use_case="lane_brief",
            target_key=target_key,
            role="assistant",
            content={"brief": result.brief.model_dump(), "tool_trace": result.tool_trace},
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            brief_id=brief_id,
        )
        agent_cache.record_cost(
            use_case="lane_brief",
            provider=result.provider,
            model=result.model,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            usd=result.cost_usd,
        )

        yield _sse("final_brief", _result_to_dict(result))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── country brief ─────────────────────────────────────────────────────────


def _country_result_to_dict(result: CountryBriefResult) -> dict:
    return result.model_dump(mode="json")


@router.get("/country-brief/{m49}")
def country_brief(
    m49: int,
    stream: bool = Query(False, description="Stream sub-agent events as SSE."),
    verify: Literal["strict", "fast", "off"] = Query(
        "strict",
        description=(
            "Reflection mode. strict = signal + band verification with caveat "
            "aggregation. fast = annotate only. off = skip."
        ),
    ),
    refresh: bool = Query(False, description="Bypass cache."),
    only_cached: bool = Query(
        False,
        description=(
            "When true, return cached brief if present or "
            "{cache_hit: false, needs_generation: true} without invoking the LLM."
        ),
    ),
    state: AppState = Depends(get_state),
):
    """Two-specialist country brief (inbound + outbound + synthesiser).

    Cache key: ``(use_case='country_brief', target_key=str(m49), snapshot_hash)``.
    """
    target_key = str(m49)
    snap = _state_snapshot_hash(state)

    cached = (
        None if refresh
        else agent_cache.get_cached_brief("country_brief", target_key, snap)
    )

    if only_cached:
        if cached:
            return {
                **cached["brief"],
                "cache_hit": True,
                "model": cached["model"],
                "provider": cached["provider"],
                "cost_usd": cached["cost_usd"],
                "latency_ms": cached["latency_ms"],
            }
        return {
            "cache_hit": False,
            "needs_generation": True,
            "target_key": target_key,
            "snapshot_hash": snap,
        }

    if cached and not stream:
        return {
            **cached["brief"],
            "cache_hit": True,
            "model": cached["model"],
            "provider": cached["provider"],
            "cost_usd": cached["cost_usd"],
            "latency_ms": cached["latency_ms"],
        }

    if not stream:
        try:
            result = generate_country_brief(m49, state=state, verify=verify)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        brief_id = agent_cache.store_brief(
            use_case="country_brief",
            target_key=target_key,
            snapshot_hash=snap,
            brief=_country_result_to_dict(result),
            model=result.model,
            provider=result.provider,
            cost_usd=result.cost_usd,
            latency_ms=result.latency_ms,
        )
        agent_cache.append_audit(
            use_case="country_brief",
            target_key=target_key,
            role="assistant",
            content={"brief": result.brief.model_dump(), "tool_trace": result.tool_trace},
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            brief_id=brief_id,
        )
        agent_cache.record_cost(
            use_case="country_brief",
            provider=result.provider,
            model=result.model,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            usd=result.cost_usd,
        )
        return _country_result_to_dict(result)

    async def event_stream() -> AsyncIterator[bytes]:
        yield _sse("status", {"phase": "starting", "target_key": target_key, "snapshot": snap})

        if cached:
            yield _sse("final_brief", cached["brief"] | {"cache_hit": True})
            return

        try:
            result = generate_country_brief(m49, state=state, verify=verify)
        except ValueError as exc:
            yield _sse("error", {"message": str(exc), "code": 404})
            return
        except RuntimeError as exc:
            yield _sse("error", {"message": str(exc), "code": 502})
            return

        # Replay tool trace grouped by sub-agent phase.
        for t in result.tool_trace:
            yield _sse(
                "tool_call",
                {
                    "name": t["name"],
                    "args": t.get("args", {}),
                    "latency_ms": t.get("latency_ms", 0),
                    "phase": t.get("phase"),
                },
            )
            yield _sse("tool_result", {"name": t["name"], "result": t.get("result", {})})

        for note in result.brief.verifier_notes:
            yield _sse("verifier_note", {"note": note})

        brief_id = agent_cache.store_brief(
            use_case="country_brief",
            target_key=target_key,
            snapshot_hash=snap,
            brief=_country_result_to_dict(result),
            model=result.model,
            provider=result.provider,
            cost_usd=result.cost_usd,
            latency_ms=result.latency_ms,
        )
        agent_cache.append_audit(
            use_case="country_brief",
            target_key=target_key,
            role="assistant",
            content={"brief": result.brief.model_dump(), "tool_trace": result.tool_trace},
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            brief_id=brief_id,
        )
        agent_cache.record_cost(
            use_case="country_brief",
            provider=result.provider,
            model=result.model,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            usd=result.cost_usd,
        )

        yield _sse("final_brief", _country_result_to_dict(result))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── period shift (Phase 3) ────────────────────────────────────────────────


def _period_shift_to_dict(result: PeriodShiftResult) -> dict:
    return result.model_dump(mode="json")


@router.get("/period-shift")
def period_shift(
    period_b: int | None = Query(
        None, description="Comparison year; defaults to the latest loaded period."
    ),
    period_a: int | None = Query(
        None, description="Baseline year; defaults to the prior period."
    ),
    stream: bool = Query(False, description="Stream events as SSE."),
    verify: Literal["strict", "fast", "off"] = Query(
        "fast",
        description="Reflection mode. fast (default) verifies + annotates; strict reruns on mismatch; off skips.",
    ),
    refresh: bool = Query(False, description="Bypass cache."),
    only_cached: bool = Query(
        False,
        description=(
            "When true, return the cached brief if present without invoking the "
            "LLM. If no cache hit, return {cache_hit: false, needs_generation: true}."
        ),
    ),
    state: AppState = Depends(get_state),
):
    """Corpus-wide period-shift diagnostic.

    Cache key: ``(use_case='period_shift', target_key='{period_a}-{period_b}', snapshot_hash)``.
    period_a and period_b default to the prior and latest loaded trade periods.
    """
    # Resolve target_key BEFORE computing anything else so cache lookups are
    # cheap and deterministic. We resolve periods using the same logic as the
    # generator so the cache key is stable.
    from defensefood.agent.briefs.period_shift import _resolve_periods

    pa, pb = _resolve_periods(state, period_b, period_a)
    target_key = f"{pa}-{pb}"
    snap = _state_snapshot_hash(state)

    cached = (
        None if refresh
        else agent_cache.get_cached_brief("period_shift", target_key, snap)
    )

    # Available periods are useful in BOTH the cache-hit and cache-miss cases
    # so the UI can render a selector regardless. They come from the same
    # ground truth the resolver uses (state.dependency_history).
    history = getattr(state, "dependency_history", None) or {}
    available_periods = sorted(
        int(p) for p, snap in history.items() if isinstance(snap, dict) and snap
    )

    if only_cached:
        if cached:
            return {
                **cached["brief"],
                "cache_hit": True,
                "model": cached["model"],
                "provider": cached["provider"],
                "cost_usd": cached["cost_usd"],
                "latency_ms": cached["latency_ms"],
                "available_periods": available_periods,
            }
        return {
            "cache_hit": False,
            "needs_generation": True,
            "target_key": target_key,
            "snapshot_hash": snap,
            "period_a": pa,
            "period_b": pb,
            "available_periods": available_periods,
        }

    if cached and not stream:
        return {
            **cached["brief"],
            "cache_hit": True,
            "model": cached["model"],
            "provider": cached["provider"],
            "cost_usd": cached["cost_usd"],
            "latency_ms": cached["latency_ms"],
        }

    if not stream:
        try:
            result = generate_period_shift_brief(
                state=state,
                period_b=pb,
                period_a=pa,
                verify=verify,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        brief_id = agent_cache.store_brief(
            use_case="period_shift",
            target_key=target_key,
            snapshot_hash=snap,
            brief=_period_shift_to_dict(result),
            model=result.model,
            provider=result.provider,
            cost_usd=result.cost_usd,
            latency_ms=result.latency_ms,
        )
        agent_cache.append_audit(
            use_case="period_shift",
            target_key=target_key,
            role="assistant",
            content={"brief": result.brief.model_dump(), "tool_trace": result.tool_trace},
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            brief_id=brief_id,
        )
        agent_cache.record_cost(
            use_case="period_shift",
            provider=result.provider,
            model=result.model,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            usd=result.cost_usd,
        )
        return _period_shift_to_dict(result)

    async def event_stream() -> AsyncIterator[bytes]:
        yield _sse(
            "status",
            {"phase": "starting", "target_key": target_key, "snapshot": snap},
        )

        if cached:
            yield _sse("final_brief", cached["brief"] | {"cache_hit": True})
            return

        try:
            result = generate_period_shift_brief(
                state=state,
                period_b=pb,
                period_a=pa,
                verify=verify,
            )
        except ValueError as exc:
            yield _sse("error", {"message": str(exc), "code": 404})
            return
        except RuntimeError as exc:
            yield _sse("error", {"message": str(exc), "code": 502})
            return

        for t in result.tool_trace:
            yield _sse(
                "tool_call",
                {"name": t["name"], "args": t["args"], "latency_ms": t["latency_ms"]},
            )
            yield _sse("tool_result", {"name": t["name"], "result": t["result"]})

        for note in result.brief.verifier_notes:
            yield _sse("verifier_note", {"note": note})

        brief_id = agent_cache.store_brief(
            use_case="period_shift",
            target_key=target_key,
            snapshot_hash=snap,
            brief=_period_shift_to_dict(result),
            model=result.model,
            provider=result.provider,
            cost_usd=result.cost_usd,
            latency_ms=result.latency_ms,
        )
        agent_cache.append_audit(
            use_case="period_shift",
            target_key=target_key,
            role="assistant",
            content={"brief": result.brief.model_dump(), "tool_trace": result.tool_trace},
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            brief_id=brief_id,
        )
        agent_cache.record_cost(
            use_case="period_shift",
            provider=result.provider,
            model=result.model,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            usd=result.cost_usd,
        )

        yield _sse("final_brief", _period_shift_to_dict(result))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Phase 5: hypotheses + anomaly explainer ──────────────────────────────


def _hypotheses_to_dict(r: HypothesisResult) -> dict:
    return r.model_dump(mode="json")


@router.get("/hypotheses/{commodity_hs}/{destination_m49}/{origin_m49}")
def hypotheses(
    commodity_hs: str,
    destination_m49: int,
    origin_m49: int,
    refresh: bool = Query(False),
    only_cached: bool = Query(
        False,
        description=(
            "Return cached set if present without invoking the LLM. Missing "
            "cache yields {cache_hit: false, needs_generation: true}."
        ),
    ),
    verify: Literal["strict", "fast", "off"] = Query("fast"),
    state: AppState = Depends(get_state),
):
    """Generate (or return cached) hypothesis set for a lane."""
    target_key = f"{commodity_hs}/{destination_m49}/{origin_m49}"
    snap = _state_snapshot_hash(state)

    cached = (
        None if refresh
        else agent_cache.get_cached_brief("hypotheses", target_key, snap)
    )

    if only_cached:
        if cached:
            return {
                **cached["brief"],
                "cache_hit": True,
                "model": cached["model"],
                "provider": cached["provider"],
                "cost_usd": cached["cost_usd"],
                "latency_ms": cached["latency_ms"],
            }
        return {
            "cache_hit": False,
            "needs_generation": True,
            "target_key": target_key,
            "snapshot_hash": snap,
        }

    if cached:
        return {
            **cached["brief"],
            "cache_hit": True,
            "model": cached["model"],
            "provider": cached["provider"],
            "cost_usd": cached["cost_usd"],
            "latency_ms": cached["latency_ms"],
        }

    try:
        result = generate_hypotheses(
            commodity_hs, destination_m49, origin_m49,
            state=state, verify=verify,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    brief_id = agent_cache.store_brief(
        use_case="hypotheses",
        target_key=target_key,
        snapshot_hash=snap,
        brief=_hypotheses_to_dict(result),
        model=result.model,
        provider=result.provider,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )
    agent_cache.append_audit(
        use_case="hypotheses",
        target_key=target_key,
        role="assistant",
        content={"hset": result.hset.model_dump(), "tool_trace": result.tool_trace},
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        brief_id=brief_id,
    )
    agent_cache.record_cost(
        use_case="hypotheses",
        provider=result.provider,
        model=result.model,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        usd=result.cost_usd,
    )
    return _hypotheses_to_dict(result)


def _anomaly_to_dict(r: AnomalyResult) -> dict:
    return r.model_dump(mode="json")


@router.get("/explain-anomaly/{commodity_hs}/{destination_m49}/{origin_m49}")
def explain_anomaly(
    commodity_hs: str,
    destination_m49: int,
    origin_m49: int,
    refresh: bool = Query(False),
    only_cached: bool = Query(False),
    verify: Literal["strict", "fast", "off"] = Query("fast"),
    state: AppState = Depends(get_state),
):
    """Generate (or return cached) anomaly explanation for a lane."""
    target_key = f"{commodity_hs}/{destination_m49}/{origin_m49}"
    snap = _state_snapshot_hash(state)

    cached = (
        None if refresh
        else agent_cache.get_cached_brief("explain_anomaly", target_key, snap)
    )

    if only_cached:
        if cached:
            return {
                **cached["brief"],
                "cache_hit": True,
                "model": cached["model"],
                "provider": cached["provider"],
                "cost_usd": cached["cost_usd"],
                "latency_ms": cached["latency_ms"],
            }
        return {
            "cache_hit": False,
            "needs_generation": True,
            "target_key": target_key,
            "snapshot_hash": snap,
        }

    if cached:
        return {
            **cached["brief"],
            "cache_hit": True,
            "model": cached["model"],
            "provider": cached["provider"],
            "cost_usd": cached["cost_usd"],
            "latency_ms": cached["latency_ms"],
        }

    try:
        result = generate_anomaly_explanation(
            commodity_hs, destination_m49, origin_m49,
            state=state, verify=verify,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    brief_id = agent_cache.store_brief(
        use_case="explain_anomaly",
        target_key=target_key,
        snapshot_hash=snap,
        brief=_anomaly_to_dict(result),
        model=result.model,
        provider=result.provider,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )
    agent_cache.append_audit(
        use_case="explain_anomaly",
        target_key=target_key,
        role="assistant",
        content={
            "explanation": result.explanation.model_dump(),
            "tool_trace": result.tool_trace,
        },
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        brief_id=brief_id,
    )
    agent_cache.record_cost(
        use_case="explain_anomaly",
        provider=result.provider,
        model=result.model,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        usd=result.cost_usd,
    )
    return _anomaly_to_dict(result)


# ── conversational Q&A (Phase 4) ──────────────────────────────────────────


class QAQuery(BaseModel):
    """Request body for ``POST /api/v1/agent/qa``."""

    query: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None


def _qa_result_to_dict(result: QAResult) -> dict:
    return result.model_dump(mode="json")


@router.post("/qa")
def qa(
    body: QAQuery,
    stream: bool = Query(
        False, description="Stream routing + tool + answer events as SSE."
    ),
    state: AppState = Depends(get_state),
):
    """Single Q&A turn against the corpus.

    Out-of-scope queries short-circuit after routing with a graceful refusal
    (no Sonnet tokens spent). In-scope queries run the composer (Sonnet)
    with the full corpus toolbox and persist the turn to the conversation
    memory.
    """
    if not stream:
        try:
            result = handle_query(
                body.query,
                state=state,
                conversation_id=body.conversation_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        return _qa_result_to_dict(result)

    async def event_stream() -> AsyncIterator[bytes]:
        yield _sse(
            "status",
            {"phase": "routing", "conversation_id": body.conversation_id},
        )
        try:
            result = handle_query(
                body.query,
                state=state,
                conversation_id=body.conversation_id,
            )
        except ValueError as exc:
            yield _sse("error", {"message": str(exc), "code": 400})
            return
        except RuntimeError as exc:
            yield _sse("error", {"message": str(exc), "code": 502})
            return

        yield _sse(
            "intent",
            result.classification.model_dump(),
        )
        if result.refused:
            yield _sse(
                "final_answer",
                _qa_result_to_dict(result),
            )
            return

        for t in result.tool_trace:
            yield _sse(
                "tool_call",
                {
                    "name": t["name"],
                    "args": t["args"],
                    "latency_ms": t["latency_ms"],
                },
            )
            yield _sse("tool_result", {"name": t["name"], "result": t["result"]})
        for note in result.turn.verifier_notes:
            yield _sse("verifier_note", {"note": note})

        yield _sse("final_answer", _qa_result_to_dict(result))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations")
def list_conversations(limit: int = Query(20, ge=1, le=100)):
    """List the most recently used Q&A conversations (headers only)."""
    return {"rows": agent_cache.list_conversations(limit=limit)}


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    """Return a conversation's full message history for the chat UI."""
    convo = agent_cache.get_conversation(conversation_id)
    if convo is None:
        raise HTTPException(
            status_code=404, detail=f"Conversation {conversation_id} not found."
        )
    return convo


# ── admin (Phase 6) — REMOVED ─────────────────────────────────────────────
#
# The admin and methodology endpoints used to live here. They were removed
# in favour of a CLI tool (``python -m script.agent_admin``) so the HTTP
# surface stays minimal and the system prompts + cost ledger are never
# reachable over the network. See backend/script/agent_admin.py.


# ── audit / evidence ──────────────────────────────────────────────────────


@router.get("/evidence/{brief_id}")
def evidence(brief_id: int):
    """Return the audit-log rows for a brief, for the 'Show evidence' expander."""
    rows = agent_cache.get_audit(brief_id)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No audit for brief {brief_id}")
    return {"brief_id": brief_id, "rows": rows}


# ── cost dashboard ────────────────────────────────────────────────────────


@router.get("/costs/today")
def costs_today():
    """Cost ledger for today, sorted by USD descending."""
    return {"rows": agent_cache.daily_costs()}
