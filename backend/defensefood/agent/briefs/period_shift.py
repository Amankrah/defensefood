"""
Period-shift diagnostic generator (Phase 3).

Compares the latest loaded period against a prior period across the corpus,
surfacing risers, fallers, and emerging clusters. The structural shape mirrors
the lane brief: a tool-use loop with pre-loaded data + forced submit + style
sanitiser + reflection pass.

Pre-loading happens server-side:

- ``compare_corpus_periods`` runs once with ``top_n=25`` so the agent has the
  top movers in one shot.
- ``detect_clusters`` runs once for the CVS-delta criterion. The agent can
  request a different criterion (e.g. notif_delta clusters) via the optional
  tool surface, but it rarely needs to.

This deliberately keeps the LLM cost near a single Sonnet round-trip per
generation.
"""

from __future__ import annotations

import json as _json
import logging
import time
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from defensefood.agent.briefs.lane_brief import _sanitise_style
from defensefood.agent.briefs.schemas import (
    CitedSignal,
    PeriodCluster,
    PeriodMover,
    PeriodShiftBrief,
)
from defensefood.agent.config import ProviderName, Tier, get_config
from defensefood.agent.provider import AgentRun, get_provider
from defensefood.agent.tools import invoke_tool, tool

logger = logging.getLogger(__name__)

VerifyMode = Literal["strict", "fast", "off"]

# Optional tools the agent may call beyond the preload.
_PERIOD_SHIFT_TOOLS: list[str] = [
    "get_corridor_profile",
    "get_methodology",
    "get_hazard_summary",
]


# ── submit_period_shift_brief: forced final-step tool ─────────────────────


@tool(
    name="submit_period_shift_brief",
    description=(
        "Submit the final period-shift diagnostic. Call exactly once. The "
        "verifier checks all corpus-aggregate signals against the pre-loaded "
        "compare_corpus_periods output."
    ),
)
def _submit_period_shift_brief(
    args: PeriodShiftBrief, *, state: Any
) -> dict[str, Any]:
    """Pass-through capture — the runner reads structured_output from the trace."""
    return args.model_dump()


# ── helpers ───────────────────────────────────────────────────────────────


def _load_system_prompt() -> str:
    cfg = get_config()
    backend_root = Path(__file__).resolve().parents[3]
    p = backend_root / cfg.prompts_dir / "period_shift.md"
    if not p.exists():
        raise FileNotFoundError(f"period_shift prompt missing: {p}")
    return p.read_text(encoding="utf-8")


def _resolve_periods(state: Any, period_b: Optional[int], period_a: Optional[int]) -> tuple[int, int]:
    """Default to the WIDEST populated window in ``state.dependency_history``.

    Defaults to (earliest_populated, latest_populated) so a researcher opening
    the dashboard sees the full multi-year shift, not just last year vs the
    year before. The caller can override either bound via query params on the
    endpoint; the UI exposes a selector backed by the populated period list.

    Resolution order:
    1. If both bounds are explicit, return them verbatim.
    2. Otherwise look at periods that actually have populated dependency
       snapshots and default the missing bound to that range's edge.
    3. Fall back to ``state.coverage['trade_periods']`` then to
       ``state.trade_period`` only when nothing else exists.
    """
    if period_b is not None and period_a is not None:
        return int(period_a), int(period_b)

    history = getattr(state, "dependency_history", None) or {}
    populated = sorted(
        int(p) for p, snap in history.items() if isinstance(snap, dict) and snap
    )

    if not populated:
        coverage = getattr(state, "coverage", None) or {}
        populated = sorted(int(p) for p in (coverage.get("trade_periods") or []))

    if not populated:
        latest = int(getattr(state, "trade_period", 0) or 0)
        return latest - 1, latest

    if len(populated) == 1:
        latest = populated[0]
        return latest - 1, latest

    # Widest window by default.
    if period_a is None:
        period_a = populated[0]
    if period_b is None:
        period_b = populated[-1]
    # If the user pinned period_b but not period_a (or vice-versa), use the
    # opposite edge of the populated range so the window stays as wide as
    # the caller's constraint allows.
    if period_a >= period_b:
        # Caller gave a degenerate range; pick the widest valid alternative.
        if period_a == period_b:
            priors = [p for p in populated if p < period_a]
            if priors:
                period_a = priors[0]
            else:
                later = [p for p in populated if p > period_b]
                if later:
                    period_b = later[-1]
        else:
            period_a, period_b = period_b, period_a
    return int(period_a), int(period_b)


def _preload_period_context(state: Any, period_a: int, period_b: int) -> dict[str, Any]:
    """Run the corpus comparisons server-side and return a compact dict."""
    deltas_call = invoke_tool(
        "compare_corpus_periods",
        {"period_a": period_a, "period_b": period_b, "top_n": 25},
        state=state,
    )
    clusters_call = invoke_tool(
        "detect_clusters",
        {
            "period_a": period_a,
            "period_b": period_b,
            "criterion": "cvs_delta",
            "group_by": "commodity_chapter_origin",
            "min_lanes": 2,
            "top_k": 6,
        },
        state=state,
    )

    out: dict[str, Any] = {
        "period_a": period_a,
        "period_b": period_b,
    }
    if deltas_call.get("ok"):
        out["compare_corpus_periods"] = deltas_call.get("result")
    if clusters_call.get("ok"):
        out["detect_clusters"] = clusters_call.get("result")
    return out


def _build_user_prompt(period_a: int, period_b: int, preload: dict[str, Any]) -> str:
    preload_json = _json.dumps(preload, ensure_ascii=False, indent=2, default=str)
    return (
        f"Write a corpus-wide period-shift diagnostic comparing {period_a} (baseline) "
        f"against {period_b} (comparison).\n\n"
        "## Pre-loaded data (already computed; do NOT re-fetch)\n\n"
        "The `compare_corpus_periods` and `detect_clusters` lookups have been\n"
        "run server-side. Read the JSON below and draft the diagnostic directly.\n\n"
        "```json\n"
        f"{preload_json}\n"
        "```\n\n"
        f"Set `period_a={period_a}` and `period_b={period_b}` on the output.\n"
        "Follow the workflow in the system prompt. Call "
        "`submit_period_shift_brief` exactly once."
    )


def _build_force_submit_prompt(
    period_a: int,
    period_b: int,
    prior_text: str,
) -> str:
    return (
        f"You previously analysed the {period_a} to {period_b} period shift but "
        "ended with text instead of calling submit_period_shift_brief. Package "
        "the work you already did as a single submit_period_shift_brief call.\n\n"
        f"Your previous draft:\n{prior_text or '(no prior text)'}\n"
    )


# ── verifier ──────────────────────────────────────────────────────────────


def _verify_corpus_signals(brief: PeriodShiftBrief, preload: dict[str, Any]) -> list[str]:
    """Cross-check brief signals against the pre-loaded totals."""
    notes: list[str] = []
    totals = (
        (preload.get("compare_corpus_periods") or {}).get("totals") or {}
    )
    mapping = {
        "corpus_corridors_compared": totals.get("corridors_compared"),
        "corpus_risers": totals.get("risers"),
        "corpus_fallers": totals.get("fallers"),
        "corpus_stable": totals.get("stable"),
        "corpus_median_cvs_delta": totals.get("median_cvs_delta"),
    }
    for sig in brief.key_signals:
        expected = mapping.get(sig.source_field)
        if expected is None:
            continue
        try:
            actual = float(sig.value) if sig.value is not None else None
            exp_f = float(expected)
        except (TypeError, ValueError):
            continue
        if actual is None:
            continue
        denom = max(abs(exp_f), 1e-2)
        if abs(actual - exp_f) / denom > 2e-2:
            notes.append(
                f"signal {sig.source_field}: brief says {sig.value} but engine has {expected}"
            )
            sig.value = exp_f
    return notes


def _check_required_caveats(brief: PeriodShiftBrief, preload: dict[str, Any]) -> list[str]:
    """Inject mandatory caveats that the prompt requires."""
    notes: list[str] = []
    existing = {c.lower() for c in brief.caveats}

    def _need(condition: bool, marker: str, message: str) -> None:
        if condition and not any(marker.lower() in c for c in existing):
            brief.caveats.append(message)
            existing.add(message.lower())
            notes.append(f"caveat injected: {marker}")

    _need(
        True,
        "data_lag",
        f"The corpus reflects trade data through {brief.period_b}; field activity "
        "since then is not in scope.",
    )

    totals = (preload.get("compare_corpus_periods") or {}).get("totals") or {}
    n = int(totals.get("corridors_compared") or 0)
    if n > 0:
        _need(
            n < 100,
            "small_population",
            f"Only {n} corridors had multi-year coverage spanning both periods; "
            "deltas reflect a small comparable population.",
        )

    # Check the top movers' cvs_mode distribution for mixed-mode caveat.
    movers = (preload.get("compare_corpus_periods") or {}).get("top_movers") or []
    sci_his_count = sum(1 for m in movers if m.get("cvs_mode") == "sci_his")
    if movers and sci_his_count / len(movers) > 0.4:
        _need(
            True,
            "mixed_modes",
            f"{sci_his_count} of the {len(movers)} top movers were scored in the "
            "sci_his fallback mode; rankings mix across CVS modes.",
        )

    return notes


def _sanitise_brief_style(brief: PeriodShiftBrief) -> list[str]:
    """Apply the shared style sanitiser across headline + body + caveats + mover/cluster explanations."""
    notes: list[str] = []

    new_headline, h_notes = _sanitise_style(brief.headline)
    brief.headline = new_headline
    notes.extend(h_notes)

    new_body, b_notes = _sanitise_style(brief.body_markdown)
    brief.body_markdown = new_body
    notes.extend(b_notes)

    new_caveats: list[str] = []
    for c in brief.caveats:
        nc, c_notes = _sanitise_style(c)
        new_caveats.append(nc)
        notes.extend(c_notes)
    brief.caveats = new_caveats

    for m in brief.top_risers + brief.top_fallers:
        ne, e_notes = _sanitise_style(m.explanation)
        m.explanation = ne
        notes.extend(e_notes)
    for cl in brief.emerging_clusters:
        ne, e_notes = _sanitise_style(cl.explanation)
        cl.explanation = ne
        notes.extend(e_notes)

    return notes


# ── public entry point ────────────────────────────────────────────────────


class PeriodShiftResult(BaseModel):
    brief: PeriodShiftBrief
    period_a: int
    period_b: int
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    cache_hit: bool = False
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)


def generate_period_shift_brief(
    *,
    state: Any,
    period_b: Optional[int] = None,
    period_a: Optional[int] = None,
    verify: VerifyMode = "fast",
    provider: Optional[ProviderName] = None,
    tier: Tier = "narrative",
    max_iters: int = 3,
) -> PeriodShiftResult:
    """Run the period-shift diagnostic pipeline.

    Caching is the caller's responsibility (the SSE endpoint wraps this with
    ``cache.get_cached_brief`` / ``cache.store_brief``).
    """
    t0 = time.perf_counter()
    pa, pb = _resolve_periods(state, period_b, period_a)
    if pa == pb:
        raise ValueError(
            f"period_a and period_b must differ; got both equal to {pa}."
        )

    system_prompt = _load_system_prompt()
    preload = _preload_period_context(state, pa, pb)

    totals = (preload.get("compare_corpus_periods") or {}).get("totals") or {}
    if not totals or int(totals.get("corridors_compared") or 0) == 0:
        available = totals.get("available_periods") or []
        in_a = int(totals.get("corridors_in_a_only") or 0)
        in_b = int(totals.get("corridors_in_b_only") or 0)
        diag = (
            f" Available dependency periods: {available}; "
            f"{in_a} corridor(s) only in {pa}, {in_b} only in {pb}."
        )
        # If the user did NOT explicitly pin periods, try to pick a better pair.
        if len(available) >= 2:
            best_a, best_b = available[-2], available[-1]
            raise ValueError(
                f"No corridors had coverage in both {pa} and {pb}; cannot synthesise."
                f"{diag} Try ?period_a={best_a}&period_b={best_b}."
            )
        raise ValueError(
            f"No corridors had coverage in both {pa} and {pb}; cannot synthesise."
            f"{diag}"
        )

    user_prompt = _build_user_prompt(pa, pb, preload)
    prov = get_provider(provider)

    run: AgentRun = prov.tool_use_loop(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_names=_PERIOD_SHIFT_TOOLS + ["submit_period_shift_brief"],
        state=state,
        tier=tier,
        max_iters=max_iters,
        max_tokens=1500,
        temperature=0.3,
    )

    # Forced-submit fallback.
    if run.structured_output is None:
        force = prov.tool_use_loop(
            system_prompt=system_prompt,
            user_prompt=user_prompt
            + "\n\n"
            + _build_force_submit_prompt(pa, pb, (run.final_text or "").strip()),
            tool_names=["submit_period_shift_brief"],
            state=state,
            tier=tier,
            max_iters=2,
            max_tokens=1500,
            temperature=0.2,
            force_tool="submit_period_shift_brief",
        )
        run.tokens_in += force.tokens_in
        run.tokens_out += force.tokens_out
        run.cost_usd += force.cost_usd
        run.tool_traces.extend(force.tool_traces)
        if force.structured_output is None:
            raise RuntimeError(
                "Agent failed to call submit_period_shift_brief even under forced "
                "tool choice. Provider may be unhealthy."
            )
        run.structured_output = force.structured_output

    try:
        brief = PeriodShiftBrief.model_validate(run.structured_output)
    except ValidationError as exc:
        raise RuntimeError(
            f"submit_period_shift_brief produced an invalid PeriodShiftBrief: {exc}"
        ) from exc

    # Always pin period_a / period_b to the resolved values.
    brief.period_a, brief.period_b = pa, pb

    # Reflection.
    if verify != "off":
        sig_notes = _verify_corpus_signals(brief, preload)
        caveat_notes = _check_required_caveats(brief, preload)
        style_notes = _sanitise_brief_style(brief)
        brief.verifier_notes = sig_notes + caveat_notes + style_notes

    latency_ms = int((time.perf_counter() - t0) * 1000)
    return PeriodShiftResult(
        brief=brief,
        period_a=pa,
        period_b=pb,
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
    "PeriodShiftBrief",
    "PeriodShiftResult",
    "VerifyMode",
    "generate_period_shift_brief",
]
