"""
Hypothesis generator (Phase 5.1).

For a single lane, the agent proposes 2 to 4 candidate explanations for the
observed pattern. Each carries a confidence label, supporting and
contradicting signals (cited from the corpus), a falsifying test
description (with tool names), and a "next data" pointer for what would
clinch the answer.

Same shape as the lane brief generator: preload + tool-use loop + force
submit + style sanitiser + reflection.

**Model tier**: defaults to ``"heavy"`` (Claude Opus 4.7) because Opus
follows the "2-4 hypotheses required, do not submit metadata-only" rule
reliably; Sonnet tends to satisfice with empty-array submissions. The
~5x cost premium is acceptable for this use case because hypotheses
are opt-in and cached. Override via the ``tier`` kwarg if you want to
A/B against Sonnet.
"""

from __future__ import annotations

import json as _json
import logging
import math
import time
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from defensefood.agent.briefs.lane_brief import _sanitise_style
from defensefood.agent.briefs.schemas import (
    Hypothesis,
    HypothesisSet,
)
from defensefood.agent.config import ProviderName, Tier, get_config
from defensefood.agent.provider import AgentRun, get_provider
from defensefood.agent.tools import invoke_tool, tool

logger = logging.getLogger(__name__)

VerifyMode = Literal["strict", "fast", "off"]

# Optional tools the agent may call beyond the preload.
_HYPOTHESES_TOOLS: list[str] = [
    "get_methodology",
    "compare_periods",
    "get_hazard_probability",
    "get_trade_anomalies",
    "country_inbound_exposure",
]

# Metrics we eagerly look up methodology + interpretation for so the agent
# has the catalogue's when_matters text without needing a tool call.
_PRELOAD_METRICS: tuple[str, ...] = (
    "cvs", "sci", "his", "hdi", "hhi", "ocs", "idr", "bdi", "dgi", "mtd",
)


# ── submit_hypotheses: forced final-step tool ───────────────────────────


# Minimum hypotheses required for a valid submission. The tool itself
# enforces this so the model sees an immediate retry instruction when it
# submits with an empty (or near-empty) array. The provider's tool-use loop
# treats ok=False as a recoverable error and lets the model self-correct.
_MIN_HYPOTHESES = 2


@tool(
    name="submit_hypotheses",
    description=(
        "Submit the final hypothesis set. The hypotheses array MUST contain "
        f"at least {_MIN_HYPOTHESES} entries (ideally 2 to 4). Submissions "
        "with fewer are rejected. Every hypothesis has flat fields only: "
        "headline (str), narrative (str), confidence (low/med/high), "
        "supporting_evidence (list of short strings), contradicting_evidence "
        "(list of short strings), falsifying_test (one string), next_data "
        "(one string). Reference metric source_field names inline in the "
        "narrative and evidence strings (e.g. 'OCS 0.5 (high band)')."
    ),
)
def _submit_hypotheses(args: HypothesisSet, *, state: Any) -> dict[str, Any]:
    if len(args.hypotheses) < _MIN_HYPOTHESES:
        raise ValueError(
            f"Submission rejected: hypotheses array contains "
            f"{len(args.hypotheses)} entries but at least {_MIN_HYPOTHESES} "
            f"are required. Provide 2 to 4 distinct candidate explanations. "
            f"If only one strong hypothesis exists, add a second 'null "
            f"hypothesis: the observed pattern is consistent with peer "
            f"behaviour and not meaningfully anomalous' as a contrast so the "
            f"researcher can weigh both readings."
        )
    return args.model_dump()


# ── helpers ─────────────────────────────────────────────────────────────


def _load_system_prompt() -> str:
    cfg = get_config()
    backend_root = Path(__file__).resolve().parents[3]
    p = backend_root / cfg.prompts_dir / "hypotheses.md"
    if not p.exists():
        raise FileNotFoundError(f"hypotheses prompt missing: {p}")
    return p.read_text(encoding="utf-8")


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


def _extract_last_submit_error(traces: Any, tool_name: str) -> str:
    """Walk the trace in reverse; return the most recent failed-args error
    for the named tool. Empty string when nothing was rejected."""
    seq = list(traces)
    for t in reversed(seq):
        if getattr(t, "name", "") != tool_name:
            continue
        result = getattr(t, "result", None) or {}
        if isinstance(result, dict) and not result.get("ok"):
            err = result.get("error") or ""
            return str(err)[:400]
    return ""


def _find_corridor(state: Any, hs: str, dest: int, origin: int) -> Optional[dict[str, Any]]:
    for c in state.corridor_metrics:
        if (
            str(c.get("commodity_hs")) == str(hs)
            and int(c.get("destination_m49") or -1) == int(dest)
            and int(c.get("origin_m49") or -1) == int(origin)
        ):
            return c
    return None


def _preload_hypothesis_context(
    state: Any, hs: str, dest: int, origin: int, corridor: dict[str, Any]
) -> dict[str, Any]:
    """Pre-fetch everything the hypothesis generator could plausibly need."""
    out: dict[str, Any] = {}

    profile = invoke_tool(
        "get_corridor_profile",
        {
            "commodity_hs": str(hs),
            "destination_m49": int(dest),
            "origin_m49": int(origin),
        },
        state=state,
    )
    if profile.get("ok"):
        out["profile"] = profile.get("result")

    notif = invoke_tool(
        "get_corridor_notifications",
        {
            "commodity_hs": str(hs),
            "destination_m49": int(dest),
            "origin_m49": int(origin),
        },
        state=state,
    )
    if notif.get("ok"):
        out["notifications"] = notif.get("result")

    # Per-metric band interpretation + methodology catalogue when_matters.
    bands: dict[str, Any] = {}
    methodology: dict[str, Any] = {}
    for field in _PRELOAD_METRICS:
        val = corridor.get(field)
        f = _coerce_float(val)
        if f is not None:
            b = invoke_tool(
                "interpret_metric_value",
                {"metric_key": field, "value": f},
                state=state,
            )
            if b.get("ok"):
                r = b.get("result") or {}
                bands[field] = {
                    "value": f,
                    "band": r.get("band"),
                    "label": r.get("verdict") or r.get("label"),
                }
        m = invoke_tool(
            "get_methodology",
            {"metric_key": field},
            state=state,
        )
        if m.get("ok"):
            entry = m.get("result") or {}
            wm = entry.get("when_matters")
            if wm:
                methodology[field] = wm
    if bands:
        out["metric_bands"] = bands
    if methodology:
        out["when_matters"] = methodology

    # Per-period dependency snapshots for this lane (when available).
    history = getattr(state, "dependency_history", None) or {}
    try:
        key = (str(hs), int(dest), int(origin))
    except (TypeError, ValueError):
        key = None
    if key is not None:
        per_period: dict[str, Any] = {}
        for period, snap in history.items():
            if not isinstance(snap, dict):
                continue
            entry = snap.get(key)
            if entry is not None:
                per_period[str(period)] = entry
        if per_period:
            out["per_period_snapshots"] = per_period

    return out


def _build_user_prompt(
    hs: str, dest: int, origin: int, corridor: dict[str, Any], preload: dict[str, Any]
) -> str:
    origin_country = corridor.get("origin_country") or f"M49={origin}"
    dest_country = corridor.get("destination_country") or f"M49={dest}"
    name = corridor.get("commodity_name") or f"HS {hs}"
    preload_json = _json.dumps(preload, ensure_ascii=False, indent=2, default=str)
    return (
        f"Propose 2 to 4 candidate explanations for the pattern observed on "
        f"the following corridor:\n\n"
        f"  Commodity: {name} (HS {hs})\n"
        f"  Origin:    {origin_country} (M49 {origin})\n"
        f"  Destination: {dest_country} (M49 {dest})\n\n"
        f"## Pre-loaded data (already computed; do NOT re-fetch)\n\n"
        f"The corridor profile, notification mix, per-metric band labels, "
        f"per-metric `when_matters` text from the methodology catalogue, "
        f"and per-period dependency snapshots are below.\n\n"
        f"```json\n{preload_json}\n```\n\n"
        f"Follow the workflow in the system prompt. End by calling "
        f"`submit_hypotheses` exactly once."
    )


# ── reflection ──────────────────────────────────────────────────────────


def _sanitise_set_style(hset: HypothesisSet) -> list[str]:
    """Apply the shared style sanitiser across every text field."""
    notes: list[str] = []

    new_summary, sum_notes = _sanitise_style(hset.pattern_summary)
    hset.pattern_summary = new_summary
    notes.extend(sum_notes)

    new_label, lbl_notes = _sanitise_style(hset.target_label)
    hset.target_label = new_label
    notes.extend(lbl_notes)

    new_caveats: list[str] = []
    for c in hset.caveats:
        nc, cn = _sanitise_style(c)
        new_caveats.append(nc)
        notes.extend(cn)
    hset.caveats = new_caveats

    for h in hset.hypotheses:
        new_headline, hn = _sanitise_style(h.headline)
        h.headline = new_headline
        notes.extend(hn)

        new_narr, nn = _sanitise_style(h.narrative)
        h.narrative = new_narr
        notes.extend(nn)

        new_test, tn = _sanitise_style(h.falsifying_test)
        h.falsifying_test = new_test
        notes.extend(tn)

        new_data, dn = _sanitise_style(h.next_data)
        h.next_data = new_data
        notes.extend(dn)

        new_sup: list[str] = []
        for s in h.supporting_evidence:
            ns, sn = _sanitise_style(s)
            new_sup.append(ns)
            notes.extend(sn)
        h.supporting_evidence = new_sup

        new_con: list[str] = []
        for s in h.contradicting_evidence:
            ns, sn = _sanitise_style(s)
            new_con.append(ns)
            notes.extend(sn)
        h.contradicting_evidence = new_con

    return notes


def _check_required_caveats(
    corridor: dict[str, Any], hset: HypothesisSet, periods_count: int
) -> list[str]:
    notes: list[str] = []
    existing = {c.lower() for c in hset.caveats}

    def _need(condition: bool, marker: str, message: str) -> None:
        if condition and not any(marker.lower() in c for c in existing):
            hset.caveats.append(message)
            existing.add(message.lower())
            notes.append(f"caveat injected: {marker}")

    _need(
        corridor.get("cvs_mode") == "sci_his",
        "sci_his",
        "Composite Vulnerability Score (CVS) computed without consumption "
        "demand because FAOSTAT FBS is unavailable; CVS-driven hypotheses "
        "are weaker on this lane.",
    )
    _need(
        corridor.get("market_presence") == "informational",
        "informational",
        "Lane is RASFF informational only; hazard-driven hypotheses are "
        "discounted because the product was not placed on the destination "
        "market.",
    )
    _need(
        periods_count < 2,
        "single_period",
        "Only one period of dependency data; period-shift hypotheses cannot "
        "be tested from this corpus alone.",
    )
    return notes


# ── public entry point ──────────────────────────────────────────────────


class HypothesisResult(BaseModel):
    """Wrapper returned by :func:`generate_hypotheses`."""

    hset: HypothesisSet
    corridor_key: str = Field(description="'hs/dest/origin' string.")
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    cache_hit: bool = False
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)


def generate_hypotheses(
    hs: str,
    dest: int,
    origin: int,
    *,
    state: Any,
    verify: VerifyMode = "fast",
    provider: Optional[ProviderName] = None,
    tier: Tier = "heavy",
    max_iters: int = 4,
) -> HypothesisResult:
    """Generate 2 to 4 candidate explanations for a corridor's pattern."""
    t0 = time.perf_counter()
    corridor = _find_corridor(state, hs, dest, origin)
    if corridor is None:
        raise ValueError(
            f"Corridor not found: hs={hs} dest={dest} origin={origin}"
        )

    system_prompt = _load_system_prompt()
    preload = _preload_hypothesis_context(state, hs, dest, origin, corridor)
    user_prompt = _build_user_prompt(hs, dest, origin, corridor, preload)
    prov = get_provider(provider)

    run: AgentRun = prov.tool_use_loop(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_names=_HYPOTHESES_TOOLS + ["submit_hypotheses"],
        state=state,
        tier=tier,
        max_iters=max_iters,
        max_tokens=2200,
        temperature=0.4,
    )

    if run.structured_output is None:
        forced_user = (
            user_prompt
            + "\n\nYour previous draft was the following text. Package it as a "
            + "single submit_hypotheses call.\n\n"
            + (run.final_text or "(no prior text)").strip()
        )
        forced = prov.tool_use_loop(
            system_prompt=system_prompt,
            user_prompt=forced_user,
            tool_names=["submit_hypotheses"],
            state=state,
            tier=tier,
            max_iters=3,
            max_tokens=2200,
            temperature=0.2,
            force_tool="submit_hypotheses",
        )
        run.tokens_in += forced.tokens_in
        run.tokens_out += forced.tokens_out
        run.cost_usd += forced.cost_usd
        run.tool_traces.extend(forced.tool_traces)
        if forced.structured_output is None:
            last_err = _extract_last_submit_error(run.tool_traces, "submit_hypotheses")
            if last_err:
                raise RuntimeError(
                    f"Hypothesis generator could not produce a valid "
                    f"HypothesisSet after the forced retry. Last validation "
                    f"error: {last_err}"
                )
            raise RuntimeError(
                "Hypothesis generator failed to call submit_hypotheses even "
                "under forced tool choice."
            )
        run.structured_output = forced.structured_output

    try:
        hset = HypothesisSet.model_validate(run.structured_output)
    except ValidationError as exc:
        raise RuntimeError(
            f"submit_hypotheses produced an invalid HypothesisSet: {exc}"
        ) from exc

    if not hset.hypotheses:
        # Model submitted only the metadata and forgot the array. Surface a
        # specific error rather than rendering an empty card.
        raise RuntimeError(
            "Hypothesis generator submitted a HypothesisSet with no "
            "hypotheses. The model likely ran out of output tokens before "
            "writing the hypothesis array; try again with a fresh request."
        )

    # Reflection. Numerical-signal verification is no longer available
    # because the flat schema stores evidence as plain strings; we rely on
    # the caveat aggregator + style sanitiser instead.
    if verify != "off":
        verifier_notes: list[str] = []
        periods_count = len(preload.get("per_period_snapshots") or {})
        verifier_notes.extend(_check_required_caveats(corridor, hset, periods_count))
        verifier_notes.extend(_sanitise_set_style(hset))
        hset.verifier_notes = verifier_notes

    latency_ms = int((time.perf_counter() - t0) * 1000)
    return HypothesisResult(
        hset=hset,
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
    "Hypothesis",
    "HypothesisResult",
    "HypothesisSet",
    "VerifyMode",
    "generate_hypotheses",
]
