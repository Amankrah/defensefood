"""
Country brief generator — Phase 2.

Multi-agent composition:

* **Inbound specialist** — runs against the inbound exposure tools and submits
  a :class:`CountryHalf` via the forced ``submit_inbound_half`` tool.
* **Outbound specialist** — runs against the outbound ORPS tools, same shape.
* The two specialists run **in parallel** (ThreadPoolExecutor) because each
  hits its own LLM call and there is no shared mutable state.
* **Synthesiser** — merges the two halves into a :class:`CountryBrief`,
  enforces dedup of signals and caveats, and submits via
  ``submit_country_brief``.

Reflection runs on the synthesised output, with the additional
country-specific caveat aggregator (sub-aggregates from inbound coverage).
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from defensefood.agent.briefs.schemas import (
    CitedSignal,
    CountryBrief,
    CountryHalf,
)
from defensefood.agent.config import ProviderName, Tier, get_config
from defensefood.agent.provider import AgentRun, get_provider
from defensefood.agent.tools import invoke_tool, tool

logger = logging.getLogger(__name__)

VerifyMode = Literal["strict", "fast", "off"]


# The exposure / ORPS lookup is pre-loaded into the user prompt for each
# specialist, so the agent does not waste an LLM round-trip retrieving the
# data the dashboard already displayed. Remaining tools are optional and
# cover broader investigation.
_INBOUND_TOOLS = [
    "get_corridor_profile",
    "list_top_corridors",
    "get_methodology",
]

_OUTBOUND_TOOLS = [
    "list_top_corridors",
    "get_methodology",
]


# ── forced submit tools ────────────────────────────────────────────────────


@tool(
    name="submit_inbound_half",
    description=(
        "Submit the inbound-half analysis. Call exactly once after gathering "
        "evidence. signals must cite the same source_field convention used in "
        "the lane brief."
    ),
)
def _submit_inbound_half(args: CountryHalf, *, state: Any) -> dict[str, Any]:
    return args.model_dump()


@tool(
    name="submit_outbound_half",
    description=(
        "Submit the outbound-half analysis. Call exactly once after gathering "
        "evidence."
    ),
)
def _submit_outbound_half(args: CountryHalf, *, state: Any) -> dict[str, Any]:
    return args.model_dump()


@tool(
    name="submit_country_brief",
    description=(
        "Submit the synthesised country brief. Call exactly once after merging "
        "the two halves. Do not invent new signals."
    ),
)
def _submit_country_brief(args: CountryBrief, *, state: Any) -> dict[str, Any]:
    return args.model_dump()


# ── helpers ────────────────────────────────────────────────────────────────


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_prompt(name: str) -> str:
    cfg = get_config()
    p = _backend_root() / cfg.prompts_dir / name
    if not p.exists():
        raise FileNotFoundError(f"Missing prompt: {p}")
    return p.read_text(encoding="utf-8")


def _country_label(state: Any, m49: int) -> str:
    for c in state.corridor_metrics:
        if int(c.get("destination_m49") or -1) == m49:
            name = c.get("destination_country")
            if name:
                return f"{name} (M49 {m49})"
        if int(c.get("origin_m49") or -1) == m49:
            name = c.get("origin_country")
            if name:
                return f"{name} (M49 {m49})"
    return f"M49 {m49}"


def _preload_country_side(state: Any, m49: int, side: str) -> dict[str, Any]:
    """Pre-fetch the inbound / outbound aggregate the dashboard already showed."""
    if side == "inbound":
        call = invoke_tool("country_inbound_exposure", {"m49": int(m49)}, state=state)
    else:
        call = invoke_tool("country_outbound_orps", {"m49": int(m49)}, state=state)
    return call.get("result") or {}


def _user_prompt(m49: int, label: str, side: str, preload: dict[str, Any]) -> str:
    import json as _json
    tool_name = "country_inbound_exposure" if side == "inbound" else "country_outbound_orps"
    preload_json = _json.dumps(preload, ensure_ascii=False, indent=2, default=str)
    return (
        f"Write the {side} half of the country brief for {label}.\n\n"
        f"## Pre-loaded data (already computed; do NOT re-fetch)\n\n"
        f"The `{tool_name}` lookup has been run server-side. Read this JSON\n"
        f"and draft the half directly. Optional tools (get_corridor_profile,\n"
        f"list_top_corridors, get_methodology) remain available only when you\n"
        f"need a value not already present.\n\n"
        f"```json\n{preload_json}\n```\n\n"
        f"Follow the workflow in the system prompt. End by calling "
        f"`submit_{side}_half` exactly once."
    )


def _has_inbound(state: Any, m49: int) -> bool:
    return any(int(c.get("destination_m49") or -1) == m49 for c in state.corridor_metrics)


def _has_outbound(state: Any, m49: int) -> bool:
    return any(int(c.get("origin_m49") or -1) == m49 for c in state.corridor_metrics)


# ── sub-agent runners ──────────────────────────────────────────────────────


def _run_specialist(
    *,
    side: Literal["inbound", "outbound"],
    m49: int,
    state: Any,
    provider_name: Optional[ProviderName],
    tier: Tier,
) -> tuple[CountryHalf, AgentRun]:
    prov = get_provider(provider_name)
    label = _country_label(state, m49)
    preload = _preload_country_side(state, m49, side)
    if side == "inbound":
        system = _load_prompt("country_brief_inbound.md")
        user = _user_prompt(m49, label, "inbound", preload)
        tool_names = _INBOUND_TOOLS + ["submit_inbound_half"]
    else:
        system = _load_prompt("country_brief_outbound.md")
        user = _user_prompt(m49, label, "outbound", preload)
        tool_names = _OUTBOUND_TOOLS + ["submit_outbound_half"]

    run = prov.tool_use_loop(
        system_prompt=system,
        user_prompt=user,
        tool_names=tool_names,
        state=state,
        tier=tier,
        max_iters=4,
        max_tokens=1200,
        temperature=0.3,
    )

    # Forced-submit fallback if specialist ended with prose.
    if run.structured_output is None:
        prior_text = (run.final_text or "").strip()
        force_user = (
            f"You previously analysed {side} exposure for {label} but ended "
            f"with text instead of calling submit_{side}_half. Package the work "
            f"as a single submit_{side}_half call.\n\n"
            f"Your previous draft:\n{prior_text or '(no prior text)'}\n"
        )
        forced = prov.tool_use_loop(
            system_prompt=system,
            user_prompt=force_user,
            tool_names=[f"submit_{side}_half"],
            state=state,
            tier=tier,
            max_iters=2,
            max_tokens=1200,
            temperature=0.2,
            force_tool=f"submit_{side}_half",
        )
        # Merge usage so cost ledger reflects the retry.
        run.tokens_in += forced.tokens_in
        run.tokens_out += forced.tokens_out
        run.cost_usd += forced.cost_usd
        run.tool_traces.extend(forced.tool_traces)
        if forced.structured_output is not None:
            run.structured_output = forced.structured_output
        else:
            return (
                CountryHalf(
                    markdown=f"({side} half could not be drafted — agent did not submit even under forced tool choice)",
                    signals=[],
                    notable_lanes=[],
                ),
                run,
            )

    try:
        half = CountryHalf.model_validate(run.structured_output)
    except ValidationError:
        half = CountryHalf(markdown=f"({side} half invalid)", signals=[], notable_lanes=[])
    return half, run


def _dedupe_signals(signals: list[CitedSignal]) -> list[CitedSignal]:
    seen: set[tuple[str, str]] = set()
    out: list[CitedSignal] = []
    for s in signals:
        key = (s.source_field, str(s.value))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _dedupe_caveats(caveats: list[str]) -> list[str]:
    out: list[str] = []
    for c in caveats:
        if not any(c.lower()[:60] in existing.lower() for existing in out):
            out.append(c)
    return out


# ── synthesiser ────────────────────────────────────────────────────────────


def _run_synthesiser(
    *,
    inbound: CountryHalf,
    outbound: CountryHalf,
    m49: int,
    state: Any,
    provider_name: Optional[ProviderName],
    tier: Tier,
) -> tuple[CountryBrief, AgentRun]:
    prov = get_provider(provider_name)
    system = _load_prompt("country_brief_synthesis.md")
    label = _country_label(state, m49)
    user = (
        f"Synthesise the country brief for {label} from the two halves below. "
        f"Do not invent signals — copy from these.\n\n"
        f"=== INBOUND HALF ===\n"
        f"{inbound.model_dump_json(indent=2)}\n\n"
        f"=== OUTBOUND HALF ===\n"
        f"{outbound.model_dump_json(indent=2)}\n\n"
        f"Call submit_country_brief exactly once."
    )
    run = prov.tool_use_loop(
        system_prompt=system,
        user_prompt=user,
        tool_names=["submit_country_brief"],
        state=state,
        tier=tier,
        max_iters=2,
        max_tokens=1200,
        temperature=0.2,
        force_tool="submit_country_brief",
    )
    if run.structured_output is None:
        # Hand-merge fallback so the call never returns empty.
        return _hand_merge(inbound, outbound), run
    try:
        brief = CountryBrief.model_validate(run.structured_output)
    except ValidationError:
        return _hand_merge(inbound, outbound), run

    # Final dedup pass: even if the model deduped, normalise once more.
    brief.key_signals = _dedupe_signals(brief.key_signals)
    brief.caveats = _dedupe_caveats(brief.caveats)
    return brief, run


def _hand_merge(inbound: CountryHalf, outbound: CountryHalf) -> CountryBrief:
    """Used when the synthesiser fails to submit — produce a best-effort merge."""
    return CountryBrief(
        headline="Inbound and outbound exposure summary.",
        inbound_markdown=inbound.markdown,
        outbound_markdown=outbound.markdown,
        key_signals=_dedupe_signals(inbound.signals + outbound.signals),
        notable_lanes=(inbound.notable_lanes + outbound.notable_lanes)[:6],
        caveats=[],
        confidence="med",
        sub_agent_notes=["synthesiser failed; hand-merged"],
    )


# ── public result type ────────────────────────────────────────────────────


class CountryBriefResult(BaseModel):
    brief: CountryBrief
    m49: int
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    cache_hit: bool = False
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)


# ── verification ───────────────────────────────────────────────────────────


def _verify_signals_against_state(brief: CountryBrief, state: Any) -> list[str]:
    """Per-signal numeric verification — uses the lane brief's verifier core."""
    from defensefood.agent.briefs.lane_brief import _coerce_float

    notes: list[str] = []
    for sig in brief.key_signals:
        # Country-level signals: ACEP / ORPS / etc. won't live on a single
        # corridor record. Skip verification when the source_field looks like
        # an aggregate; the agent should still cite the value, but auditing
        # requires cross-tool replay (a Phase 6 concern).
        AGGREGATE_FIELDS = {
            "acep", "acep_confirmed", "acep_detected", "acep_informational",
            "orps", "orps_confirmed", "total_inbound_corridors",
            "total_outbound_corridors", "country_coverage",
        }
        if sig.source_field in AGGREGATE_FIELDS:
            continue
        # If the field maps to a corridor field, look for ANY corridor with
        # that field at the cited value (within tolerance). This is weaker
        # than the lane verifier but appropriate for country aggregations.
        if isinstance(sig.value, (int, float)):
            target = _coerce_float(sig.value)
            if target is None:
                continue
            any_match = False
            for c in state.corridor_metrics:
                cv = _coerce_float(c.get(sig.source_field))
                if cv is None:
                    continue
                if abs(cv - target) / max(abs(cv), 1e-2) < 1e-2:
                    any_match = True
                    break
            if not any_match:
                notes.append(
                    f"signal {sig.source_field}={sig.value}: no matching corridor found"
                )
    return notes


def _check_band_consistency(brief: CountryBrief, state: Any) -> list[str]:
    """Out-of-band claim detection: every signal's band must match interpret_metric."""
    notes: list[str] = []
    for sig in brief.key_signals:
        if not isinstance(sig.value, (int, float)):
            continue
        if sig.band == "unknown":
            continue
        try:
            r = invoke_tool(
                "interpret_metric_value",
                {"metric_key": sig.source_field, "value": float(sig.value)},
                state=state,
            )
        except Exception:
            continue
        if not r.get("ok"):
            continue
        engine_band = (r.get("result") or {}).get("band")
        if engine_band and engine_band != sig.band:
            notes.append(
                f"signal {sig.source_field} claimed band={sig.band} but engine says {engine_band}"
            )
            sig.band = engine_band  # auto-correct
    return notes


def _sanitise_country_brief_style(brief: CountryBrief) -> list[str]:
    """Apply the lane-brief style sanitiser across both halves + headline + caveats."""
    from defensefood.agent.briefs.lane_brief import _sanitise_style

    all_notes: list[str] = []

    new_headline, h_notes = _sanitise_style(brief.headline)
    brief.headline = new_headline
    all_notes.extend(h_notes)

    new_in, in_notes = _sanitise_style(brief.inbound_markdown)
    brief.inbound_markdown = new_in
    all_notes.extend(in_notes)

    new_out, out_notes = _sanitise_style(brief.outbound_markdown)
    brief.outbound_markdown = new_out
    all_notes.extend(out_notes)

    new_caveats: list[str] = []
    for c in brief.caveats:
        nc, c_notes = _sanitise_style(c)
        new_caveats.append(nc)
        all_notes.extend(c_notes)
    brief.caveats = new_caveats

    return all_notes


def _country_caveat_aggregator(brief: CountryBrief, state: Any, m49: int) -> list[str]:
    """Inject country-level caveats based on aggregated data quality."""
    notes: list[str] = []
    existing = {c.lower() for c in brief.caveats}

    def _need(condition: bool, marker: str, message: str) -> None:
        if condition and not any(marker.lower() in c for c in existing):
            brief.caveats.append(message)
            existing.add(message.lower())
            notes.append(f"caveat injected: {marker}")

    inbound = [c for c in state.corridor_metrics if int(c.get("destination_m49") or -1) == m49]
    if inbound:
        n_sci_his = sum(1 for c in inbound if c.get("cvs_mode") == "sci_his")
        if n_sci_his / max(len(inbound), 1) > 0.3:
            _need(
                True,
                "sci_his",
                f"{n_sci_his} of {len(inbound)} inbound lanes computed CVS in the "
                "sci_his fallback (FAOSTAT FBS gap); inbound rankings are mixed across modes.",
            )
        n_informational = sum(1 for c in inbound if c.get("market_presence") == "informational")
        if n_informational / max(len(inbound), 1) > 0.2:
            _need(
                True,
                "informational",
                f"{n_informational} of {len(inbound)} inbound lanes are RASFF "
                "informational-only mentions; structural metrics shown for transparency only.",
            )

    return notes


# ── public entry point ────────────────────────────────────────────────────


def generate_country_brief(
    m49: int,
    *,
    state: Any,
    verify: VerifyMode = "fast",
    provider: Optional[ProviderName] = None,
    tier: Tier = "narrative",
) -> CountryBriefResult:
    """Run the two-specialist + synthesiser pipeline for a country."""
    t0 = time.perf_counter()
    label = _country_label(state, m49)

    has_in = _has_inbound(state, m49)
    has_out = _has_outbound(state, m49)
    if not has_in and not has_out:
        raise ValueError(f"No corridors for {label}; nothing to brief.")

    runs: dict[str, AgentRun] = {}
    halves: dict[str, CountryHalf] = {}
    sub_notes: list[str] = []

    # Run the specialists in parallel.
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures: dict[str, Any] = {}
        if has_in:
            futures["inbound"] = ex.submit(
                _run_specialist,
                side="inbound",
                m49=m49,
                state=state,
                provider_name=provider,
                tier=tier,
            )
        else:
            halves["inbound"] = CountryHalf(
                markdown="No inbound corridors in the loaded corpus.", signals=[], notable_lanes=[]
            )
            sub_notes.append("inbound specialist skipped — no inbound corridors")
        if has_out:
            futures["outbound"] = ex.submit(
                _run_specialist,
                side="outbound",
                m49=m49,
                state=state,
                provider_name=provider,
                tier=tier,
            )
        else:
            halves["outbound"] = CountryHalf(
                markdown="No outbound corridors in the loaded corpus.", signals=[], notable_lanes=[]
            )
            sub_notes.append("outbound specialist skipped — no outbound corridors")

        for side, fut in futures.items():
            half, run = fut.result()
            halves[side] = half
            runs[side] = run
            sub_notes.append(f"{side} specialist OK ({run.model})")

    # Synthesise.
    brief, syn_run = _run_synthesiser(
        inbound=halves["inbound"],
        outbound=halves["outbound"],
        m49=m49,
        state=state,
        provider_name=provider,
        tier=tier,
    )
    runs["synthesiser"] = syn_run

    # Always carry sub-agent provenance so the UI can show it.
    brief.sub_agent_notes = sub_notes + brief.sub_agent_notes

    # Reflection.
    if verify != "off":
        sig_notes = _verify_signals_against_state(brief, state)
        band_notes = _check_band_consistency(brief, state)
        caveat_notes = _country_caveat_aggregator(brief, state, m49)
        style_notes = _sanitise_country_brief_style(brief)
        brief.verifier_notes = sig_notes + band_notes + caveat_notes + style_notes

    # Aggregate cost + tokens across all sub-runs.
    total_in = sum(r.tokens_in for r in runs.values())
    total_out = sum(r.tokens_out for r in runs.values())
    total_cost = sum(r.cost_usd for r in runs.values())
    tool_trace = []
    for tag, r in runs.items():
        for t in r.tool_traces:
            tool_trace.append(
                {
                    "phase": tag,
                    "name": t.name,
                    "args": t.args,
                    "result": t.result,
                    "latency_ms": t.latency_ms,
                }
            )

    return CountryBriefResult(
        brief=brief,
        m49=m49,
        provider=runs.get("synthesiser", next(iter(runs.values()))).provider,
        model=runs.get("synthesiser", next(iter(runs.values()))).model,
        tokens_in=total_in,
        tokens_out=total_out,
        cost_usd=total_cost,
        latency_ms=int((time.perf_counter() - t0) * 1000),
        tool_trace=tool_trace,
    )


__all__ = [
    "CountryBrief",
    "CountryBriefResult",
    "VerifyMode",
    "generate_country_brief",
]
