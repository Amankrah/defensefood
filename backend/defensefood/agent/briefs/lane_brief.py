"""
Lane forensic brief generator.

Two passes:

1. **Drafting**: a tool-use loop that fetches the corridor profile, methodology
   entries, period comparisons, and notifications as needed, then submits a
   structured :class:`LaneBrief` via the forced ``submit_lane_brief`` tool.
2. **Reflection** (when ``verify="strict"`` or ``"fast"``): a verifier re-fetches
   every ``CitedSignal.value`` from ``AppState`` and either auto-corrects small
   discrepancies, re-runs the drafting pass with feedback (verify=strict only),
   or annotates the brief with verifier notes (verify=fast).
"""

from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from defensefood.agent.briefs.schemas import CitedSignal, LaneBrief
from defensefood.agent.config import ProviderName, Tier, get_config
from defensefood.agent.provider import AgentRun, get_provider
from defensefood.agent.tools import (
    TOOL_REGISTRY,
    ToolSpec,
    invoke_tool,
    tool,
)

logger = logging.getLogger(__name__)

VerifyMode = Literal["strict", "fast", "off"]

# Tools the agent may use while drafting.
_LANE_DRAFT_TOOLS: list[str] = [
    "get_corridor_profile",
    "get_methodology",
    "interpret_metric_value",
    "compare_periods",
    "get_corridor_notifications",
    "get_hazard_probability",
    "get_trade_anomalies",
    "country_inbound_exposure",
]


# ── submit_lane_brief: forced final-step tool ─────────────────────────────


@tool(
    name="submit_lane_brief",
    description=(
        "Submit the final lane brief. Call exactly once after gathering evidence. "
        "Every numerical claim in body_markdown must appear in key_signals with a "
        "matching source_field; the verifier re-fetches each value."
    ),
)
def _submit_lane_brief(args: LaneBrief, *, state: Any) -> dict[str, Any]:
    """Pass-through capture — the runner reads structured_output from the trace."""
    return args.model_dump()


# ── prompt loading ────────────────────────────────────────────────────────


def _load_system_prompt() -> str:
    cfg = get_config()
    backend_root = Path(__file__).resolve().parents[3]
    prompt_path = backend_root / cfg.prompts_dir / "lane_brief.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Lane brief prompt missing: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


# ── corridor key + lookup helpers ─────────────────────────────────────────


def _find_corridor(state: Any, hs: str, dest: int, origin: int) -> Optional[dict[str, Any]]:
    for c in state.corridor_metrics:
        if (
            str(c.get("commodity_hs")) == str(hs)
            and int(c.get("destination_m49") or -1) == int(dest)
            and int(c.get("origin_m49") or -1) == int(origin)
        ):
            return c
    return None


def _coerce_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


# ── user prompt construction ──────────────────────────────────────────────


def _build_user_prompt(hs: str, dest: int, origin: int, corridor: dict[str, Any]) -> str:
    origin_country = corridor.get("origin_country") or f"M49={origin}"
    dest_country = corridor.get("destination_country") or f"M49={dest}"
    name = corridor.get("commodity_name") or f"HS {hs}"
    return (
        f"Write a lane forensic brief for the corridor:\n\n"
        f"  Commodity: {name} (HS {hs})\n"
        f"  Origin:    {origin_country} (M49 {origin})\n"
        f"  Destination: {dest_country} (M49 {dest})\n\n"
        f"Follow the workflow in the system prompt. End by calling "
        f"submit_lane_brief exactly once."
    )


# ── reflection / verifier ─────────────────────────────────────────────────


def _verify_signals(
    brief: LaneBrief,
    corridor: dict[str, Any],
    *,
    tolerance: float = 1e-3,
) -> list[str]:
    """Compare each CitedSignal against the corridor record. Return notes."""
    notes: list[str] = []
    for sig in brief.key_signals:
        actual = corridor.get(sig.source_field)
        if isinstance(sig.value, (int, float)) and isinstance(actual, (int, float)):
            af = _coerce_float(actual)
            cf = _coerce_float(sig.value)
            if af is None and cf is None:
                continue
            if af is None or cf is None:
                notes.append(
                    f"signal {sig.source_field}: value present in brief but not in corridor record"
                )
                continue
            # Relative tolerance for non-zero magnitudes, absolute below 1e-2.
            denom = max(abs(af), 1e-2)
            if abs(af - cf) / denom > tolerance:
                notes.append(
                    f"signal {sig.source_field}: brief says {sig.value} but engine has {actual}"
                )
                # Auto-correct on the structured output.
                sig.value = af
        elif sig.value is not None and actual is not None:
            if str(sig.value) != str(actual):
                notes.append(
                    f"signal {sig.source_field}: brief says {sig.value!r} but engine has {actual!r}"
                )
                sig.value = actual
        elif sig.value is None and actual is not None:
            notes.append(f"signal {sig.source_field}: brief value is null but engine has {actual!r}")
            sig.value = actual
        elif actual is None and sig.value is not None:
            notes.append(
                f"signal {sig.source_field}: brief asserts a value but the field is null on this lane"
            )
    return notes


def _check_required_caveats(corridor: dict[str, Any], brief: LaneBrief) -> list[str]:
    """Append missing required caveats; return notes about what was added."""
    notes: list[str] = []
    existing = {c.lower() for c in brief.caveats}

    def _need(condition: bool, marker: str, message: str) -> None:
        if condition and not any(marker.lower() in c for c in existing):
            brief.caveats.append(message)
            existing.add(message.lower())
            notes.append(f"caveat injected: {marker}")

    _need(
        corridor.get("cvs_mode") == "sci_his",
        "sci_his",
        "CVS computed in the sci_his fallback mode because FAOSTAT FBS did not "
        "provide CRS for this destination commodity; the score is comparable "
        "to other sci_his lanes but not to full-mode lanes.",
    )
    _need(
        corridor.get("market_presence") == "informational",
        "informational",
        "Per EU RASFF SOPs this lane is informational only — the product was not "
        "placed on this destination's market — so structural metrics are shown for "
        "transparency but should not drive priority decisions.",
    )
    _need(
        corridor.get("provenance") == "trade_only",
        "trade_only",
        "Domestic supply DS' is the trade-only proxy (M − X) because FAOSTAT "
        "production data is unavailable for this commodity-country.",
    )
    _need(
        bool(corridor.get("idr_gt_1")),
        "idr_gt_1",
        "IDR > 1 indicates imports exceed apparent domestic supply, consistent "
        "with a re-export hub or missing production data.",
    )
    return notes


# ── public entry point ────────────────────────────────────────────────────


class LaneBriefResult(BaseModel):
    """Wrapper returned by :func:`generate_lane_brief`."""

    brief: LaneBrief
    corridor_key: str = Field(description="Cache-friendly 'hs/dest/origin' string.")
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    cache_hit: bool = False
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)


def generate_lane_brief(
    hs: str,
    dest: int,
    origin: int,
    *,
    state: Any,
    verify: VerifyMode = "strict",
    provider: Optional[ProviderName] = None,
    tier: Tier = "narrative",
    max_iters: int = 8,
) -> LaneBriefResult:
    """Run the lane brief draft + reflection pipeline.

    Caching is the caller's responsibility (the SSE endpoint wraps this with
    ``cache.get_cached_brief`` / ``cache.store_brief``).
    """
    t0 = time.perf_counter()
    corridor = _find_corridor(state, hs, dest, origin)
    if corridor is None:
        raise ValueError(
            f"Corridor not found: hs={hs} dest={dest} origin={origin}"
        )

    system_prompt = _load_system_prompt()
    user_prompt = _build_user_prompt(hs, dest, origin, corridor)
    prov = get_provider(provider)

    # First pass: draft. Force the agent to end at submit_lane_brief.
    run: AgentRun = prov.tool_use_loop(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_names=_LANE_DRAFT_TOOLS + ["submit_lane_brief"],
        state=state,
        tier=tier,
        max_iters=max_iters,
        max_tokens=2200,
        temperature=0.3,
    )

    if run.structured_output is None:
        # Agent finished without calling submit_lane_brief; surface a stub.
        raise RuntimeError(
            "Agent did not call submit_lane_brief; transcript ended with text. "
            "This usually means the tool budget was exhausted before drafting."
        )

    try:
        brief = LaneBrief.model_validate(run.structured_output)
    except ValidationError as exc:
        raise RuntimeError(
            f"submit_lane_brief produced an invalid LaneBrief: {exc}"
        ) from exc

    # Reflection pass.
    if verify != "off":
        notes = _verify_signals(brief, corridor)
        notes.extend(_check_required_caveats(corridor, brief))
        brief.verifier_notes = notes

        # Strict mode: if there are hard mismatches, re-run with feedback.
        hard_mismatches = [n for n in notes if "engine has" in n]
        if verify == "strict" and hard_mismatches:
            feedback = (
                "The previous draft contained signal mismatches against the engine:\n"
                + "\n".join(f"- {n}" for n in hard_mismatches[:6])
                + "\nDraft a new lane brief that uses the corrected values. Same lane."
            )
            run2 = prov.tool_use_loop(
                system_prompt=system_prompt,
                user_prompt=user_prompt + "\n\n" + feedback,
                tool_names=_LANE_DRAFT_TOOLS + ["submit_lane_brief"],
                state=state,
                tier=tier,
                max_iters=max_iters,
                max_tokens=2200,
                temperature=0.2,
            )
            if run2.structured_output is not None:
                try:
                    brief = LaneBrief.model_validate(run2.structured_output)
                    brief.verifier_notes = ["strict reflection triggered rerun"] + (
                        _verify_signals(brief, corridor)
                        + _check_required_caveats(corridor, brief)
                    )
                    # Merge usage / cost.
                    run.tokens_in += run2.tokens_in
                    run.tokens_out += run2.tokens_out
                    run.cost_usd += run2.cost_usd
                    run.tool_traces.extend(run2.tool_traces)
                except ValidationError:
                    brief.verifier_notes.append(
                        "rerun produced invalid LaneBrief; kept first draft"
                    )

    latency_ms = int((time.perf_counter() - t0) * 1000)
    return LaneBriefResult(
        brief=brief,
        corridor_key=f"{hs}/{dest}/{origin}",
        provider=run.provider,
        model=run.model,
        tokens_in=run.tokens_in,
        tokens_out=run.tokens_out,
        cost_usd=run.cost_usd,
        latency_ms=latency_ms,
        cache_hit=False,
        tool_trace=[
            {
                "name": t.name,
                "args": t.args,
                "result": t.result,
                "latency_ms": t.latency_ms,
            }
            for t in run.tool_traces
        ],
    )


__all__ = [
    "LaneBrief",
    "LaneBriefResult",
    "VerifyMode",
    "generate_lane_brief",
]
