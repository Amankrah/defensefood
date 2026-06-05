"""
Anomaly explainer (Phase 5.3).

Deeper than the standard lane brief: pulls multi-period dependency history,
the methodology catalogue's ``when_matters`` text, peer summary (other lanes
in the same commodity chapter at the same destination role), and asks the
agent to deliver a verdict (anomalous / borderline / not_anomalous) along
with explicit "why anomalous" + "why not" paragraphs.

Designed so the structured output is a labelling input for the future
predictive subsystem: anomaly verdicts become training labels, the
supporting_signals become feature anchors.
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
    AnomalyExplanation,
    CitedSignal,
)
from defensefood.agent.config import ProviderName, Tier, get_config
from defensefood.agent.provider import AgentRun, get_provider
from defensefood.agent.tools import invoke_tool, tool

logger = logging.getLogger(__name__)

VerifyMode = Literal["strict", "fast", "off"]

_ANOMALY_TOOLS: list[str] = [
    "get_methodology",
    "compare_periods",
    "get_hazard_probability",
    "get_trade_anomalies",
]

_PRELOAD_METRICS: tuple[str, ...] = (
    "cvs", "sci", "his", "hdi", "hhi", "ocs", "idr", "bdi", "dgi", "mtd",
)

# Hard cap on peers we summarise so the prompt stays bounded.
_MAX_PEERS = 8


# ── submit_anomaly_explanation: forced final-step tool ─────────────────────


@tool(
    name="submit_anomaly_explanation",
    description=(
        "Submit the anomaly verdict + supporting evidence. Call exactly "
        "once. Every numerical claim in why_anomalous or why_not must "
        "appear in supporting_signals."
    ),
)
def _submit_anomaly_explanation(
    args: AnomalyExplanation, *, state: Any
) -> dict[str, Any]:
    return args.model_dump()


# ── helpers ─────────────────────────────────────────────────────────────


def _load_system_prompt() -> str:
    cfg = get_config()
    backend_root = Path(__file__).resolve().parents[3]
    p = backend_root / cfg.prompts_dir / "anomaly_explainer.md"
    if not p.exists():
        raise FileNotFoundError(f"anomaly_explainer prompt missing: {p}")
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


def _find_corridor(state: Any, hs: str, dest: int, origin: int) -> Optional[dict[str, Any]]:
    for c in state.corridor_metrics:
        if (
            str(c.get("commodity_hs")) == str(hs)
            and int(c.get("destination_m49") or -1) == int(dest)
            and int(c.get("origin_m49") or -1) == int(origin)
        ):
            return c
    return None


def _peer_summary(
    state: Any, corridor: dict[str, Any]
) -> list[dict[str, Any]]:
    """Find lanes at the same commodity chapter + destination role.

    Returns a compact list of peer dicts the prompt can show: lane key,
    origin, key metrics. Bounded by _MAX_PEERS.
    """
    hs = str(corridor.get("commodity_hs") or "")
    if not hs:
        return []
    chapter = hs[:2]
    dest = int(corridor.get("destination_m49") or -1)
    target_presence = corridor.get("market_presence")

    self_key = (
        str(corridor.get("commodity_hs")),
        int(corridor.get("destination_m49") or -1),
        int(corridor.get("origin_m49") or -1),
    )

    peers: list[dict[str, Any]] = []
    for c in state.corridor_metrics:
        if (
            str(c.get("commodity_hs")),
            int(c.get("destination_m49") or -1),
            int(c.get("origin_m49") or -1),
        ) == self_key:
            continue
        chs = str(c.get("commodity_hs") or "")
        if chs[:2] != chapter:
            continue
        if int(c.get("destination_m49") or -1) != dest:
            continue
        # Prefer same market_presence to keep the peer set comparable.
        if target_presence and c.get("market_presence") != target_presence:
            continue
        peers.append(
            {
                "lane_key": f"{chs}/{c.get('destination_m49')}/{c.get('origin_m49')}",
                "origin_country": c.get("origin_country"),
                "commodity_name": c.get("commodity_name"),
                "cvs": _coerce_float(c.get("cvs")),
                "sci": _coerce_float(c.get("sci")),
                "his": _coerce_float(c.get("his")),
                "ocs": _coerce_float(c.get("ocs")),
                "idr": _coerce_float(c.get("idr")),
                "notification_count": c.get("notification_count"),
                "market_presence": c.get("market_presence"),
            }
        )
    # Sort by descending CVS so the most-comparable peers come first.
    peers.sort(key=lambda p: (p.get("cvs") or 0.0), reverse=True)
    return peers[:_MAX_PEERS]


def _preload_anomaly_context(
    state: Any, hs: str, dest: int, origin: int, corridor: dict[str, Any]
) -> dict[str, Any]:
    """Pre-fetch corridor, notifications, methodology, multi-period, peers."""
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

    bands: dict[str, Any] = {}
    when_matters: dict[str, str] = {}
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
                when_matters[field] = wm
    if bands:
        out["metric_bands"] = bands
    if when_matters:
        out["when_matters"] = when_matters

    # Per-period dependency snapshots.
    history = getattr(state, "dependency_history", None) or {}
    per_period: dict[str, Any] = {}
    try:
        key = (str(hs), int(dest), int(origin))
    except (TypeError, ValueError):
        key = None
    if key is not None:
        for period, snap in history.items():
            if not isinstance(snap, dict):
                continue
            entry = snap.get(key)
            if entry is not None:
                per_period[str(period)] = entry
    if per_period:
        out["per_period_snapshots"] = per_period

    # Notification cadence by year (from notifications_by_corridor).
    notifs_by_lane = getattr(state, "notifications_by_corridor", None) or {}
    rows = notifs_by_lane.get(key) if key is not None else None
    if rows:
        year_counts: dict[int, int] = {}
        for r in rows:
            p_raw = int(r.get("period") or 0)
            if p_raw <= 0:
                continue
            year = p_raw // 100 if p_raw >= 100000 else p_raw
            year_counts[year] = year_counts.get(year, 0) + 1
        if year_counts:
            out["notification_cadence_by_year"] = dict(sorted(year_counts.items()))

    # Peer summary.
    peers = _peer_summary(state, corridor)
    if peers:
        out["peers"] = peers

    return out


def _build_user_prompt(
    hs: str, dest: int, origin: int, corridor: dict[str, Any], preload: dict[str, Any]
) -> str:
    origin_country = corridor.get("origin_country") or f"M49={origin}"
    dest_country = corridor.get("destination_country") or f"M49={dest}"
    name = corridor.get("commodity_name") or f"HS {hs}"
    preload_json = _json.dumps(preload, ensure_ascii=False, indent=2, default=str)
    return (
        f"Decide whether the following corridor is anomalous and explain "
        f"both sides of the question:\n\n"
        f"  Commodity: {name} (HS {hs})\n"
        f"  Origin:    {origin_country} (M49 {origin})\n"
        f"  Destination: {dest_country} (M49 {dest})\n\n"
        f"## Pre-loaded data (already computed; do NOT re-fetch)\n\n"
        f"Corridor profile, notification mix, per-metric bands and "
        f"`when_matters` text, per-period snapshots, notification cadence by "
        f"year, and a peer summary (same commodity chapter, same destination, "
        f"same market presence) are below.\n\n"
        f"```json\n{preload_json}\n```\n\n"
        f"Follow the workflow in the system prompt. End by calling "
        f"`submit_anomaly_explanation` exactly once."
    )


# ── reflection ──────────────────────────────────────────────────────────


def _verify_signals(
    signals: list[CitedSignal], corridor: dict[str, Any], tolerance: float = 2e-2
) -> list[str]:
    notes: list[str] = []
    for sig in signals:
        actual = corridor.get(sig.source_field)
        if isinstance(sig.value, (int, float)) and isinstance(actual, (int, float)):
            af = _coerce_float(actual)
            cf = _coerce_float(sig.value)
            if af is None or cf is None:
                continue
            denom = max(abs(af), 1e-2)
            if abs(af - cf) / denom > tolerance:
                notes.append(
                    f"signal {sig.source_field}: claim={sig.value} engine={actual}"
                )
                sig.value = af
    return notes


def _check_required_caveats(
    corridor: dict[str, Any], expl: AnomalyExplanation, periods_count: int
) -> list[str]:
    notes: list[str] = []
    existing = {c.lower() for c in expl.caveats}

    def _need(condition: bool, marker: str, message: str) -> None:
        if condition and not any(marker.lower() in c for c in existing):
            expl.caveats.append(message)
            existing.add(message.lower())
            notes.append(f"caveat injected: {marker}")

    _need(
        corridor.get("cvs_mode") == "sci_his",
        "sci_his",
        "Composite Vulnerability Score (CVS) computed without consumption "
        "demand; structural anomaly readings remain valid but composite-score-"
        "driven readings are weaker.",
    )
    _need(
        corridor.get("market_presence") == "informational",
        "informational",
        "Lane is RASFF informational only; the hazard side of the anomaly "
        "check is qualitative, not quantitative.",
    )
    _need(
        corridor.get("provenance") == "trade_only",
        "trade_only",
        "Domestic supply is the trade-only proxy; Import Dependency Ratio "
        "(IDR) above 1 may reflect missing production data.",
    )
    _need(
        periods_count < 2,
        "single_period",
        "Single-period snapshot; the cross-period drift axis of the anomaly "
        "check is unavailable.",
    )
    return notes


def _sanitise_explanation_style(expl: AnomalyExplanation) -> list[str]:
    notes: list[str] = []

    new_headline, hn = _sanitise_style(expl.headline)
    expl.headline = new_headline
    notes.extend(hn)

    new_why, wn = _sanitise_style(expl.why_anomalous)
    expl.why_anomalous = new_why
    notes.extend(wn)

    new_why_not, wnn = _sanitise_style(expl.why_not)
    expl.why_not = new_why_not
    notes.extend(wnn)

    new_peer, pn = _sanitise_style(expl.peer_comparison)
    expl.peer_comparison = new_peer
    notes.extend(pn)

    new_label, ln = _sanitise_style(expl.target_label)
    expl.target_label = new_label
    notes.extend(ln)

    new_caveats: list[str] = []
    for c in expl.caveats:
        nc, cn = _sanitise_style(c)
        new_caveats.append(nc)
        notes.extend(cn)
    expl.caveats = new_caveats

    return notes


# ── public entry point ──────────────────────────────────────────────────


class AnomalyResult(BaseModel):
    """Wrapper returned by :func:`generate_anomaly_explanation`."""

    explanation: AnomalyExplanation
    corridor_key: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    cache_hit: bool = False
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)


def generate_anomaly_explanation(
    hs: str,
    dest: int,
    origin: int,
    *,
    state: Any,
    verify: VerifyMode = "fast",
    provider: Optional[ProviderName] = None,
    tier: Tier = "narrative",
    max_iters: int = 4,
) -> AnomalyResult:
    """Run the anomaly-explainer pipeline for one lane."""
    t0 = time.perf_counter()
    corridor = _find_corridor(state, hs, dest, origin)
    if corridor is None:
        raise ValueError(
            f"Corridor not found: hs={hs} dest={dest} origin={origin}"
        )

    system_prompt = _load_system_prompt()
    preload = _preload_anomaly_context(state, hs, dest, origin, corridor)
    user_prompt = _build_user_prompt(hs, dest, origin, corridor, preload)
    prov = get_provider(provider)

    run: AgentRun = prov.tool_use_loop(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_names=_ANOMALY_TOOLS + ["submit_anomaly_explanation"],
        state=state,
        tier=tier,
        max_iters=max_iters,
        max_tokens=1800,
        temperature=0.35,
    )

    if run.structured_output is None:
        forced_user = (
            user_prompt
            + "\n\nYour previous draft was the following text. Package it as a "
            + "single submit_anomaly_explanation call.\n\n"
            + (run.final_text or "(no prior text)").strip()
        )
        forced = prov.tool_use_loop(
            system_prompt=system_prompt,
            user_prompt=forced_user,
            tool_names=["submit_anomaly_explanation"],
            state=state,
            tier=tier,
            max_iters=2,
            max_tokens=1800,
            temperature=0.2,
            force_tool="submit_anomaly_explanation",
        )
        run.tokens_in += forced.tokens_in
        run.tokens_out += forced.tokens_out
        run.cost_usd += forced.cost_usd
        run.tool_traces.extend(forced.tool_traces)
        if forced.structured_output is None:
            raise RuntimeError(
                "Anomaly explainer failed to call submit_anomaly_explanation "
                "even under forced tool choice."
            )
        run.structured_output = forced.structured_output

    try:
        expl = AnomalyExplanation.model_validate(run.structured_output)
    except ValidationError as exc:
        raise RuntimeError(
            f"submit_anomaly_explanation produced an invalid AnomalyExplanation: {exc}"
        ) from exc

    if verify != "off":
        notes = _verify_signals(expl.supporting_signals, corridor)
        periods_count = len(preload.get("per_period_snapshots") or {})
        notes.extend(_check_required_caveats(corridor, expl, periods_count))
        notes.extend(_sanitise_explanation_style(expl))
        expl.verifier_notes = notes

    latency_ms = int((time.perf_counter() - t0) * 1000)
    return AnomalyResult(
        explanation=expl,
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
    "AnomalyExplanation",
    "AnomalyResult",
    "VerifyMode",
    "generate_anomaly_explanation",
]
