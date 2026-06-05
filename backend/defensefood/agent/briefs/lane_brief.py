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


# ── forced-submit fallback helpers ────────────────────────────────────────


def _summarise_tool_traces(traces: list[Any]) -> str:
    """Compact one-line per tool call for the forced-submit context."""
    if not traces:
        return "(no tools called in the prior pass)"
    lines: list[str] = []
    for t in traces[:8]:
        try:
            name = getattr(t, "name", "?")
            args = getattr(t, "args", {}) or {}
            result = getattr(t, "result", {}) or {}
            args_str = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:4])
            if isinstance(result, dict):
                ok = result.get("ok")
                if "result" in result and isinstance(result["result"], dict):
                    keys = list(result["result"].keys())[:6]
                    summary = f"keys={keys}"
                else:
                    summary = f"ok={ok}"
            else:
                summary = "(opaque)"
            lines.append(f"- {name}({args_str}) -> {summary}")
        except Exception:
            continue
    return "\n".join(lines)


def _build_force_submit_prompt(
    hs: str,
    dest: int,
    origin: int,
    corridor: dict[str, Any],
    prior_text: str,
    prior_findings: str,
) -> str:
    """Prompt for the forced submit_lane_brief retry.

    The agent already explored on the first pass; we just need it to package
    the answer as a structured tool call.
    """
    origin_country = corridor.get("origin_country") or f"M49={origin}"
    dest_country = corridor.get("destination_country") or f"M49={dest}"
    name = corridor.get("commodity_name") or f"HS {hs}"
    head = (
        f"You previously drafted a lane forensic brief but ended with text "
        f"instead of calling submit_lane_brief. Package the work you already "
        f"did as a single submit_lane_brief call.\n\n"
        f"  Commodity: {name} (HS {hs})\n"
        f"  Origin:    {origin_country} (M49 {origin})\n"
        f"  Destination: {dest_country} (M49 {dest})\n\n"
    )
    prior_block = (
        "Your previous draft (use these claims, refine the wording, and ensure "
        "every numeric value appears in key_signals):\n\n"
        f"{prior_text or '(no prior text — synthesise from findings below)'}\n"
    )
    findings_block = f"\nPrior tool findings:\n{prior_findings}\n"
    return head + prior_block + findings_block


# ── style scanner ─────────────────────────────────────────────────────────

# Words / phrases the system prompt forbids. Case-insensitive substring match.
_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "critically,",
    "importantly,",
    "notably,",
    "in summary,",
    "it is worth noting",
    "it's worth noting",
    "of particular interest",
    "furthermore,",
    "moreover,",
    "interestingly,",
    "consistent with",
    "this corridor",
    "this lane",
    "researchers should",
    "analysts should",
    "could potentially",
    "possibly indicate",
)


def _sanitise_style(text: str) -> tuple[str, list[str]]:
    """Strip em-dashes / en-dashes and report forbidden phrases.

    The em-dash replacement is mechanical (turns ` — ` into `, ` and ` – `
    into `, `). Forbidden phrases are reported but not rewritten because
    automatic replacement risks producing nonsense; the next agent run will
    see the verifier note and self-correct.
    """
    if not text:
        return text, []
    notes: list[str] = []
    cleaned = text
    # Em-dash (U+2014) and en-dash (U+2013). Strip when used as punctuation
    # surrounded by whitespace. A bare dash inside a word like "data-driven"
    # already uses U+002D (hyphen) and is untouched.
    if "—" in cleaned or "–" in cleaned:
        notes.append("style: em/en-dash replaced with comma")
        cleaned = cleaned.replace(" — ", ", ")
        cleaned = cleaned.replace(" – ", ", ")
        # Catch unspaced em-dash too.
        cleaned = cleaned.replace("—", ", ")
        cleaned = cleaned.replace("–", ", ")
    lower = cleaned.lower()
    for phrase in _FORBIDDEN_PHRASES:
        if phrase in lower:
            notes.append(f"style: forbidden phrase used: {phrase!r}")
    return cleaned, notes


def _sanitise_brief_style(brief: LaneBrief) -> list[str]:
    """Apply style sanitisation in place across headline + body + caveats."""
    all_notes: list[str] = []
    new_headline, h_notes = _sanitise_style(brief.headline)
    brief.headline = new_headline
    all_notes.extend(h_notes)
    new_body, b_notes = _sanitise_style(brief.body_markdown)
    brief.body_markdown = new_body
    all_notes.extend(b_notes)
    new_caveats: list[str] = []
    for c in brief.caveats:
        nc, c_notes = _sanitise_style(c)
        new_caveats.append(nc)
        all_notes.extend(c_notes)
    brief.caveats = new_caveats
    return all_notes


# ── reflection / verifier ─────────────────────────────────────────────────


def _verify_signals(
    brief: LaneBrief,
    corridor: dict[str, Any],
    *,
    tolerance: float = 2e-2,
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
    verify: VerifyMode = "fast",
    provider: Optional[ProviderName] = None,
    tier: Tier = "narrative",
    max_iters: int = 4,
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

    # First pass: draft. The agent explores with read tools and is expected to
    # finish by calling submit_lane_brief on its own.
    run: AgentRun = prov.tool_use_loop(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_names=_LANE_DRAFT_TOOLS + ["submit_lane_brief"],
        state=state,
        tier=tier,
        max_iters=max_iters,
        max_tokens=1500,
        temperature=0.3,
    )

    # Fallback: if the model ended with prose instead of calling
    # submit_lane_brief, do a forced second pass. The user prompt carries the
    # prior draft text and any tool findings so the model has the same context
    # it just produced — it just needs to package the answer as a tool call.
    if run.structured_output is None:
        prior_text = (run.final_text or "").strip()
        prior_findings = _summarise_tool_traces(run.tool_traces)
        force_user_prompt = _build_force_submit_prompt(
            hs, dest, origin, corridor, prior_text, prior_findings
        )
        forced = prov.tool_use_loop(
            system_prompt=system_prompt,
            user_prompt=force_user_prompt,
            tool_names=["submit_lane_brief"],
            state=state,
            tier=tier,
            max_iters=2,
            max_tokens=1500,
            temperature=0.2,
            force_tool="submit_lane_brief",
        )
        # Merge usage / traces so cost is honest.
        run.tokens_in += forced.tokens_in
        run.tokens_out += forced.tokens_out
        run.cost_usd += forced.cost_usd
        run.tool_traces.extend(forced.tool_traces)
        if forced.structured_output is None:
            raise RuntimeError(
                "Agent failed to call submit_lane_brief even under forced tool "
                "choice. Provider may be unhealthy."
            )
        run.structured_output = forced.structured_output

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
        notes.extend(_sanitise_brief_style(brief))
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
                max_tokens=1500,
                temperature=0.2,
            )
            if run2.structured_output is not None:
                try:
                    brief = LaneBrief.model_validate(run2.structured_output)
                    brief.verifier_notes = ["strict reflection triggered rerun"] + (
                        _verify_signals(brief, corridor)
                        + _check_required_caveats(corridor, brief)
                        + _sanitise_brief_style(brief)
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
