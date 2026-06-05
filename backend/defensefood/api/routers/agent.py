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

from defensefood.agent import cache as agent_cache
from defensefood.agent.briefs.lane_brief import (
    LaneBriefResult,
    VerifyMode,
    generate_lane_brief,
)
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
