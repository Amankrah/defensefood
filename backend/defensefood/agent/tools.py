"""
Tool registry for the agent subsystem.

A "tool" is a typed Python function the agent can call inside a tool-use loop.
Tool functions:

* Take a Pydantic args model as their single declared argument plus an
  implicit ``state`` keyword that the runner injects (read-only ``AppState``).
* Return a JSON-serialisable dict (or list of dicts).
* Are registered via the :func:`tool` decorator into :data:`TOOL_REGISTRY`.

Schemas are produced automatically from the Pydantic model and are compatible
with both Anthropic's ``tools=[...]`` and OpenAI's
``tools=[{type: "function", function: ...}]`` shapes — see
:func:`anthropic_schemas` and :func:`openai_schemas`.

Tools read from ``AppState`` directly (no HTTP roundtrip). The runner passes
the current state object to every tool invocation so each call sees a
consistent snapshot.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Generic,
    Literal,
    Optional,
    Protocol,
    TypeVar,
    cast,
    get_type_hints,
)

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ── types ──────────────────────────────────────────────────────────────────


class HasAppState(Protocol):
    """Minimal contract a tool sees. The real backend AppState satisfies this."""

    corridor_metrics: list[dict[str, Any]]
    # The rest is read by-name when needed; tools that need richer access
    # accept the real AppState type and benefit from full typing.


ArgsT = TypeVar("ArgsT", bound=BaseModel)


@dataclass(frozen=True)
class ToolSpec:
    """Runtime descriptor for a registered tool."""

    name: str
    description: str
    args_model: type[BaseModel]
    func: Callable[..., Any]

    def json_schema(self) -> dict[str, Any]:
        """JSON Schema for the args model (Pydantic-native)."""
        schema = self.args_model.model_json_schema()
        # Pydantic 2 may include ``$defs``; both Anthropic and OpenAI accept it,
        # but flatten the title field for cleaner UIs.
        schema.pop("title", None)
        return schema


TOOL_REGISTRY: dict[str, ToolSpec] = {}


# ── decorator ──────────────────────────────────────────────────────────────


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a tool function.

    The wrapped function MUST be signature::

        def fn(args: SomePydanticModel, *, state: AppState) -> dict | list:
            ...

    The name defaults to the function name; the description defaults to the
    function's docstring's first line.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        tool_name = name or func.__name__
        doc = (func.__doc__ or "").strip()
        first_line = doc.splitlines()[0] if doc else ""
        tool_desc = description or first_line or func.__name__

        # Inspect args: first non-state positional/keyword must be a Pydantic model.
        sig = inspect.signature(func)
        hints = get_type_hints(func)
        args_model: Optional[type[BaseModel]] = None
        for param_name, param in sig.parameters.items():
            if param_name == "state":
                continue
            ann = hints.get(param_name)
            if isinstance(ann, type) and issubclass(ann, BaseModel):
                args_model = ann
                break
        if args_model is None:
            raise TypeError(
                f"Tool {func.__name__!r}: first non-state argument must be typed "
                f"as a Pydantic BaseModel subclass."
            )

        if tool_name in TOOL_REGISTRY:
            raise ValueError(f"Tool name collision: {tool_name!r}")

        TOOL_REGISTRY[tool_name] = ToolSpec(
            name=tool_name,
            description=tool_desc,
            args_model=args_model,
            func=func,
        )
        # Stamp the descriptor on the function for callers who want it.
        func.__tool_spec__ = TOOL_REGISTRY[tool_name]  # type: ignore[attr-defined]
        return func

    return decorator


# ── invocation ─────────────────────────────────────────────────────────────


def invoke_tool(
    name: str,
    raw_args: dict[str, Any],
    *,
    state: Any,
) -> dict[str, Any]:
    """Validate ``raw_args`` against the tool's args model and run it.

    Returns a dict ``{ok, result | error}`` so callers can pass the response
    straight back to the LLM without raising. Pydantic ValidationError is
    captured and surfaced to the model so it can self-correct on the next turn.
    """
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        return {"ok": False, "error": f"Unknown tool: {name!r}"}
    try:
        args = spec.args_model.model_validate(raw_args)
    except Exception as exc:
        return {"ok": False, "error": f"Argument validation failed: {exc}"}
    try:
        result = spec.func(args, state=state)
    except ValueError as exc:
        # ValueError from a tool is the expected control-flow signal that
        # the args were business-logic-invalid (e.g. submit_hypotheses
        # rejecting an empty array). The model self-corrects on the next
        # iteration; no stack trace needed.
        logger.info("Tool %s rejected args: %s", name, exc)
        return {"ok": False, "error": f"ValueError: {exc}"}
    except Exception as exc:  # noqa: BLE001 — broad on purpose; surface to LLM
        # Anything else is a real bug — full traceback to the log.
        logger.exception("Tool %s raised", name)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "result": result}


# ── provider-specific schema shapes ────────────────────────────────────────


def anthropic_schemas(
    names: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Return tools list in Anthropic's ``[{name, description, input_schema}]``."""
    selected = [TOOL_REGISTRY[n] for n in names] if names else list(TOOL_REGISTRY.values())
    return [
        {
            "name": s.name,
            "description": s.description,
            "input_schema": s.json_schema(),
        }
        for s in selected
    ]


def openai_schemas(
    names: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Return tools list in OpenAI's ``[{type: "function", function: {...}}]``."""
    selected = [TOOL_REGISTRY[n] for n in names] if names else list(TOOL_REGISTRY.values())
    return [
        {
            "type": "function",
            "function": {
                "name": s.name,
                "description": s.description,
                "parameters": s.json_schema(),
            },
        }
        for s in selected
    ]


# ── tool implementations ──────────────────────────────────────────────────
# These read directly from AppState. Each tool's args model lives next to it
# so the decorator can infer the JSON Schema.

from pydantic import Field  # noqa: E402  (kept close to the args models)


class CorridorKey(BaseModel):
    """A single corridor key. All three fields are required."""

    commodity_hs: str = Field(description="HS code, e.g. '30771' or '100630'.")
    destination_m49: int = Field(description="UN M49 code for the destination country.")
    origin_m49: int = Field(description="UN M49 code for the origin country.")


def _find_corridor(state: Any, hs: str, dest: int, origin: int) -> Optional[dict[str, Any]]:
    for c in state.corridor_metrics:
        if (
            str(c.get("commodity_hs")) == str(hs)
            and int(c.get("destination_m49") or -1) == int(dest)
            and int(c.get("origin_m49") or -1) == int(origin)
        ):
            return c
    return None


@tool(description="Fetch the full metric record for one corridor (commodity_hs, destination, origin).")
def get_corridor_profile(args: CorridorKey, *, state: Any) -> dict[str, Any]:
    """Return the corridor's flat metric dict (Section 2-7 fields)."""
    found = _find_corridor(state, args.commodity_hs, args.destination_m49, args.origin_m49)
    if found is None:
        return {
            "found": False,
            "commodity_hs": args.commodity_hs,
            "destination_m49": args.destination_m49,
            "origin_m49": args.origin_m49,
        }
    # Return a shallow copy so tools never mutate state.
    return {"found": True, **found}


class TopCorridorsArgs(BaseModel):
    by: str = Field(
        default="cvs",
        description=(
            "Metric to sort by. Common: cvs, his, sci, bdi, severity_total, "
            "notification_count."
        ),
    )
    n: int = Field(default=10, ge=1, le=100)
    destination_m49: Optional[int] = Field(
        default=None,
        description="Optional filter: only corridors with this destination.",
    )
    origin_m49: Optional[int] = Field(
        default=None,
        description="Optional filter: only corridors with this origin.",
    )
    market_presence: Optional[str] = Field(
        default=None,
        description="Optional filter: 'confirmed', 'detected', or 'informational'.",
    )


@tool(description="List the top-N corridors sorted by a metric, with optional filters.")
def list_top_corridors(args: TopCorridorsArgs, *, state: Any) -> list[dict[str, Any]]:
    """Top-N corridors. Returns a compact list (key fields only)."""
    rows = state.corridor_metrics
    if args.destination_m49 is not None:
        rows = [c for c in rows if int(c.get("destination_m49") or -1) == args.destination_m49]
    if args.origin_m49 is not None:
        rows = [c for c in rows if int(c.get("origin_m49") or -1) == args.origin_m49]
    if args.market_presence is not None:
        rows = [c for c in rows if c.get("market_presence") == args.market_presence]

    def _val(c: dict[str, Any]) -> float:
        v = c.get(args.by)
        try:
            return float(v) if v is not None else float("-inf")
        except (TypeError, ValueError):
            return float("-inf")

    rows = sorted(rows, key=_val, reverse=True)[: args.n]
    keep = [
        "commodity_hs",
        "commodity_name",
        "destination_m49",
        "destination_country",
        "origin_m49",
        "origin_country",
        "cvs",
        "cvs_mode",
        "his",
        "hdi",
        "sci",
        "bdi",
        "notification_count",
        "severity_total",
        "market_presence",
        "data_quality",
    ]
    return [{k: c.get(k) for k in keep} for c in rows]


class MethodologyKey(BaseModel):
    metric_key: str = Field(
        description=(
            "Catalogue key, e.g. 'cvs', 'idr', 'his', 'sci', 'acep', 'pas', "
            "'sccs', 'hazard_probability', 'corridor_membership'."
        ),
    )


@tool(description="Return the methodology catalogue entry for a metric (formula, scale bands, when_matters).")
def get_methodology(args: MethodologyKey, *, state: Any) -> dict[str, Any]:
    """Look up a metric in the methodology catalogue."""
    from defensefood.api.methodology_catalogue import METHODOLOGY_BY_KEY

    entry = METHODOLOGY_BY_KEY.get(args.metric_key)
    if entry is None:
        return {"found": False, "metric_key": args.metric_key}
    return {"found": True, **entry}


class InterpretArgs(BaseModel):
    metric_key: str
    value: float


@tool(description="Map a raw metric value to its scale band, verdict, and advice.")
def interpret_metric_value(args: InterpretArgs, *, state: Any) -> dict[str, Any]:
    """Look up the scale band for a value of a known metric."""
    from defensefood.pipeline.interpretation import interpret_metric

    return interpret_metric(args.metric_key, args.value)


class M49Arg(BaseModel):
    m49: int = Field(description="UN M49 country code.")


@tool(description="Inbound exposure profile for a country (ACEP, role-split, top inbound lanes).")
def country_inbound_exposure(args: M49Arg, *, state: Any) -> dict[str, Any]:
    """Sum and rank inbound corridors for ``m49``."""
    from defensefood.api.routers.countries import get_country_acep

    payload = get_country_acep(args.m49, state)
    # Add the top 5 inbound corridors for narrative grounding.
    inbound = [
        c for c in state.corridor_metrics
        if int(c.get("destination_m49") or -1) == args.m49
    ]
    inbound.sort(key=lambda c: c.get("his") or 0, reverse=True)
    payload["top_inbound"] = [
        {
            "commodity_hs": c.get("commodity_hs"),
            "commodity_name": c.get("commodity_name"),
            "origin_m49": c.get("origin_m49"),
            "origin_country": c.get("origin_country"),
            "his": c.get("his"),
            "cvs": c.get("cvs"),
            "market_presence": c.get("market_presence"),
            "notification_count": c.get("notification_count"),
        }
        for c in inbound[:5]
    ]
    return payload


@tool(description="Outbound risk propagation (ORPS) per commodity for a country acting as origin.")
def country_outbound_orps(args: M49Arg, *, state: Any) -> dict[str, Any]:
    """Per-commodity ORPS for ``m49`` as origin."""
    from defensefood.api.routers.countries import get_orps_by_commodity

    return get_orps_by_commodity(args.m49, state)


class HazardSummaryArgs(BaseModel):
    pass


@tool(description="Corpus-wide RASFF summary: notification counts, role distribution, market presence breakdown.")
def get_hazard_summary(args: HazardSummaryArgs, *, state: Any) -> dict[str, Any]:
    """Wrap GET /hazards/summary in-process."""
    from defensefood.api.routers.hazards import get_rasff_summary

    return get_rasff_summary(state)


@tool(description="Raw RASFF notifications underlying the HIS calculation for a corridor.")
def get_corridor_notifications(args: CorridorKey, *, state: Any) -> dict[str, Any]:
    """Return raw alert rows for ``(hs, dest, origin)``, sorted by period desc."""
    from defensefood.api.routers.corridors import get_corridor_notifications as _impl

    return _impl(args.commodity_hs, args.destination_m49, args.origin_m49, state)


@tool(description="Empirical hazard probability P(hazard|trade) for a corridor — Eq.35.")
def get_hazard_probability(args: CorridorKey, *, state: Any) -> dict[str, Any]:
    """Wrap the /hazard-probability endpoint in-process."""
    from defensefood.api.routers.corridors import get_corridor_hazard_probability

    return get_corridor_hazard_probability(
        args.commodity_hs, args.destination_m49, args.origin_m49, state
    )


@tool(description="On-demand Section 5 trade-flow metrics (z_uv, z_volume, MTD, ΔHHI, ΔOCS) for a corridor.")
def get_trade_anomalies(args: CorridorKey, *, state: Any) -> dict[str, Any]:
    """Compute trade anomalies (slower; uses trade_df)."""
    from defensefood.api.routers.corridors import get_trade_anomalies as _impl

    return _impl(args.commodity_hs, args.destination_m49, args.origin_m49, state)


class TimeSeriesArgs(BaseModel):
    commodity_hs: str
    destination_m49: int
    origin_m49: int


@tool(description="Per-period dependency snapshots + monthly notification counts for a corridor.")
def get_corridor_time_series(args: TimeSeriesArgs, *, state: Any) -> dict[str, Any]:
    """Wrap the /time-series endpoint."""
    from defensefood.api.routers.corridors import get_corridor_time_series as _impl

    return _impl(
        args.commodity_hs, args.destination_m49, args.origin_m49, state=state
    )


class ComparePeriodsArgs(BaseModel):
    commodity_hs: str
    destination_m49: int
    origin_m49: int
    period_a: int = Field(description="Baseline year, e.g. 2022.")
    period_b: int = Field(description="Comparison year, e.g. 2023.")


@tool(description="Compare a corridor's BDI/OCS/HHI between two years.")
def compare_periods(args: ComparePeriodsArgs, *, state: Any) -> dict[str, Any]:
    """Diff two periods on a corridor; returns deltas + direction labels."""
    # Reuse the time-series tool's data path.
    from defensefood.api.routers.corridors import get_corridor_time_series as _ts

    ts = _ts(
        args.commodity_hs, args.destination_m49, args.origin_m49, state=state
    )
    if not isinstance(ts, dict):
        return {"ok": False, "error": "time-series unavailable"}
    by_period = ts.get("dependency_by_period") or {}

    def _snap(year: int) -> dict[str, Any]:
        return by_period.get(str(year), {})

    a = _snap(args.period_a)
    b = _snap(args.period_b)

    def _delta(k: str) -> Optional[float]:
        va, vb = a.get(k), b.get(k)
        try:
            return float(vb) - float(va) if va is not None and vb is not None else None
        except (TypeError, ValueError):
            return None

    return {
        "commodity_hs": args.commodity_hs,
        "destination_m49": args.destination_m49,
        "origin_m49": args.origin_m49,
        "period_a": args.period_a,
        "period_b": args.period_b,
        "snapshot_a": a,
        "snapshot_b": b,
        "deltas": {
            "bdi": _delta("bdi"),
            "ocs": _delta("ocs"),
            "hhi": _delta("hhi"),
            "idr": _delta("idr"),
            "sci": _delta("sci"),
        },
    }


class CoverageArgs(BaseModel):
    pass


@tool(description="Corpus-wide data-coverage diagnostics (counts by Section, missing-input reasons).")
def get_data_coverage(args: CoverageArgs, *, state: Any) -> dict[str, Any]:
    """Return the cached coverage dict (computed at startup)."""
    return dict(state.coverage) if isinstance(state.coverage, dict) else {"empty": True}


# ── Phase 3: corpus-wide period shift tools ───────────────────────────────


class CompareCorpusPeriodsArgs(BaseModel):
    period_a: int = Field(description="Baseline year, e.g. 2022.")
    period_b: int = Field(description="Comparison year, e.g. 2023.")
    top_n: int = Field(
        default=15,
        description="Cap on returned corridors; sorted by |cvs_delta| descending.",
    )
    min_notification_count: int = Field(
        default=0,
        description=(
            "Optional: only include corridors with at least this many notifications "
            "in either period. Useful to focus on lanes with real signal."
        ),
    )


@tool(description="Corpus-wide period shift: per-corridor BDI/OCS/HHI/IDR/notification deltas between two years. Pre-computes the dataset the period-shift brief needs.")
def compare_corpus_periods(
    args: CompareCorpusPeriodsArgs, *, state: Any
) -> dict[str, Any]:
    """Compute per-corridor deltas by direct lookup against state.dependency_history.

    ``state.dependency_history`` is built at startup as ``{period: {(hs, dest,
    origin): metric_dict}}`` for every period in the trade corpus. We look up
    each corridor in both periods directly and compute deltas where both are
    present.

    Returns a dict shaped like::

        {
            "period_a": 2022,
            "period_b": 2023,
            "totals": {
                "corridors_compared": 412,
                "corridors_in_a_only": 18,
                "corridors_in_b_only": 22,
                "available_periods": [2018, ..., 2023],
                "risers": 47, "fallers": 33, "stable": 332,
                "median_cvs_delta": 0.001,
            },
            "top_movers": [ ... ]
        }
    """

    def _to_float(v: Any) -> Optional[float]:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        import math
        if math.isnan(f) or math.isinf(f):
            return None
        return f

    history = getattr(state, "dependency_history", None) or {}
    available_periods = sorted(int(p) for p in history.keys())

    snap_a = history.get(int(args.period_a)) or {}
    snap_b = history.get(int(args.period_b)) or {}

    # Pre-build per-lane, per-year notification counts so we can attach real
    # notif_a / notif_b deltas. dependency_history snapshots do NOT include
    # notification_count (the dependency pipeline only computes Section 2).
    # RASFF notification periods are encoded as YYYY*100 + month, so the
    # year is period // 100.
    notif_by_lane_year: dict[tuple[Any, int, int], dict[int, int]] = {}
    for lane_key, rows_for_lane in (
        getattr(state, "notifications_by_corridor", None) or {}
    ).items():
        counts: dict[int, int] = {}
        for r in rows_for_lane or []:
            try:
                p_raw = int(r.get("period") or 0)
            except (TypeError, ValueError):
                continue
            if p_raw <= 0:
                continue
            # Heuristic: if period > 100000, it's YYYYMM; if smaller, it's
            # already YYYY.
            year = p_raw // 100 if p_raw >= 100000 else p_raw
            counts[year] = counts.get(year, 0) + 1
        if counts:
            notif_by_lane_year[lane_key] = counts

    rows: list[dict[str, Any]] = []
    risers = fallers = stable = 0
    in_a_only = in_b_only = 0

    for c in state.corridor_metrics:
        # Build the lookup key. dependency_history keys are tuples that match
        # corridor_metrics field types verbatim (built in dependencies.py).
        try:
            key = (
                c["commodity_hs"],
                int(c["destination_m49"]),
                int(c["origin_m49"]),
            )
        except (KeyError, TypeError, ValueError):
            continue

        a = snap_a.get(key)
        b = snap_b.get(key)
        if a is None and b is None:
            continue
        if a is None:
            in_b_only += 1
            continue
        if b is None:
            in_a_only += 1
            continue

        if args.min_notification_count > 0:
            nc = int(c.get("notification_count") or 0)
            if nc < args.min_notification_count:
                continue

        cvs_a = _to_float(a.get("cvs"))
        cvs_b = _to_float(b.get("cvs"))
        cvs_delta = (cvs_b - cvs_a) if (cvs_a is not None and cvs_b is not None) else None

        # Notification counts come from the RASFF index (not the dependency
        # snapshot — that pipeline only computes Section 2 structural metrics).
        lane_notifs = notif_by_lane_year.get(key, {})
        notif_a = int(lane_notifs.get(int(args.period_a), 0))
        notif_b = int(lane_notifs.get(int(args.period_b), 0))

        structural: dict[str, Optional[float]] = {}
        for k in ("bdi", "ocs", "hhi", "idr", "sci", "his"):
            va, vb = _to_float(a.get(k)), _to_float(b.get(k))
            structural[k] = (
                round(vb - va, 4)
                if (va is not None and vb is not None)
                else None
            )

        # Classification: CVS delta is the primary signal when available;
        # fall back to notification delta + structural composite when not.
        direction = "stable"
        notif_delta = notif_b - notif_a
        sci_delta = structural.get("sci")
        composite_proxy = None
        if cvs_delta is not None:
            composite_proxy = cvs_delta
        elif notif_delta or (sci_delta is not None and abs(sci_delta) > 0.1):
            # Light proxy: half the structural SCI shift plus a notification term.
            composite_proxy = (sci_delta or 0.0) * 0.3 + (notif_delta * 0.02)

        if composite_proxy is not None:
            if composite_proxy > 0.03:
                direction = "rising"
                risers += 1
            elif composite_proxy < -0.03:
                direction = "falling"
                fallers += 1
            else:
                stable += 1
        else:
            stable += 1

        rows.append(
            {
                "commodity_hs": c.get("commodity_hs"),
                "destination_m49": c.get("destination_m49"),
                "origin_m49": c.get("origin_m49"),
                "origin_country": c.get("origin_country"),
                "destination_country": c.get("destination_country"),
                "commodity_name": c.get("commodity_name"),
                "commodity_chapter": (
                    str(c.get("commodity_hs") or "")[:2]
                    if c.get("commodity_hs")
                    else None
                ),
                "cvs_a": round(cvs_a, 4) if cvs_a is not None else None,
                "cvs_b": round(cvs_b, 4) if cvs_b is not None else None,
                "cvs_delta": round(cvs_delta, 4) if cvs_delta is not None else None,
                "composite_proxy_delta": (
                    round(composite_proxy, 4) if composite_proxy is not None else None
                ),
                "notif_a": notif_a,
                "notif_b": notif_b,
                "notif_delta": notif_b - notif_a,
                "structural_deltas": structural,
                "direction": direction,
                "cvs_mode": c.get("cvs_mode"),
                "market_presence": c.get("market_presence"),
                "provenance": c.get("provenance"),
            }
        )

    # Sort by best-available movement signal: CVS delta when present, else
    # the composite proxy (structural + notification), else notif_delta alone.
    def _sort_key(r: dict[str, Any]) -> float:
        for k in ("cvs_delta", "composite_proxy_delta"):
            v = r.get(k)
            if v is not None:
                return abs(float(v))
        return abs(float(r.get("notif_delta") or 0))

    rows_sorted = sorted(rows, key=_sort_key, reverse=True)
    top_movers = rows_sorted[: int(args.top_n)]

    deltas = [r["cvs_delta"] for r in rows if r.get("cvs_delta") is not None]
    median = sorted(deltas)[len(deltas) // 2] if deltas else None

    return {
        "period_a": args.period_a,
        "period_b": args.period_b,
        "totals": {
            "corridors_compared": len(rows),
            "corridors_in_a_only": in_a_only,
            "corridors_in_b_only": in_b_only,
            "available_periods": available_periods,
            "risers": risers,
            "fallers": fallers,
            "stable": stable,
            "median_cvs_delta": round(median, 4) if median is not None else None,
        },
        "top_movers": top_movers,
    }


class DetectClustersArgs(BaseModel):
    period_a: int
    period_b: int
    criterion: Literal["cvs_delta", "notif_delta", "bdi_delta", "ocs_delta", "hhi_delta"] = Field(
        default="cvs_delta",
        description="Metric whose movement defines the cluster.",
    )
    group_by: Literal["commodity_chapter", "commodity_chapter_origin", "origin"] = Field(
        default="commodity_chapter_origin",
        description=(
            "How to define a cluster. commodity_chapter_origin pairs the HS prefix "
            "with the origin country; commodity_chapter groups across origins; "
            "origin groups across all commodities from one country."
        ),
    )
    min_lanes: int = Field(default=2, description="Minimum lanes in a cluster.")
    top_k: int = Field(default=5, description="How many clusters to return.")


@tool(description="Group corpus deltas into clusters where multiple lanes moved together; sort by aggregate movement magnitude. Pre-computes the cluster list the period-shift brief needs.")
def detect_clusters(args: DetectClustersArgs, *, state: Any) -> dict[str, Any]:
    """Run compare_corpus_periods, then bucket movers by group_by."""
    base = compare_corpus_periods(
        CompareCorpusPeriodsArgs(
            period_a=args.period_a, period_b=args.period_b, top_n=500
        ),
        state=state,
    )

    def _key(r: dict[str, Any]) -> Optional[tuple]:
        chap = r.get("commodity_chapter")
        org = r.get("origin_m49")
        org_name = r.get("origin_country")
        if args.group_by == "commodity_chapter":
            return (chap,) if chap else None
        if args.group_by == "origin":
            return (org, org_name) if org else None
        # commodity_chapter_origin
        return (chap, org, org_name) if chap and org else None

    def _value(r: dict[str, Any]) -> Optional[float]:
        # Map criterion to row field.
        if args.criterion == "cvs_delta":
            return r.get("cvs_delta")
        if args.criterion == "notif_delta":
            v = r.get("notif_delta")
            return float(v) if v is not None else None
        if args.criterion in ("bdi_delta", "ocs_delta", "hhi_delta"):
            return (r.get("structural_deltas") or {}).get(
                args.criterion.split("_delta")[0]
            )
        return None

    groups: dict[tuple, list[dict[str, Any]]] = {}
    for r in base.get("top_movers", []):
        k = _key(r)
        if k is None:
            continue
        v = _value(r)
        if v is None:
            continue
        groups.setdefault(k, []).append({"row": r, "value": float(v)})

    clusters: list[dict[str, Any]] = []
    for k, members in groups.items():
        if len(members) < args.min_lanes:
            continue
        values = [m["value"] for m in members]
        same_direction = all(v > 0 for v in values) or all(v < 0 for v in values)
        mean = sum(values) / len(values)
        clusters.append(
            {
                "key": list(k),
                "lane_count": len(members),
                "criterion": args.criterion,
                "mean_movement": round(mean, 4),
                "max_movement": round(max(values, key=abs), 4),
                "same_direction": same_direction,
                "lanes": [
                    {
                        "lane_key": (
                            f"{m['row'].get('commodity_hs')}/"
                            f"{m['row'].get('destination_m49')}/"
                            f"{m['row'].get('origin_m49')}"
                        ),
                        "movement": m["value"],
                    }
                    for m in members[:5]
                ],
            }
        )

    clusters_sorted = sorted(
        clusters,
        key=lambda c: abs(c["mean_movement"]) * c["lane_count"],
        reverse=True,
    )

    return {
        "period_a": args.period_a,
        "period_b": args.period_b,
        "criterion": args.criterion,
        "group_by": args.group_by,
        "clusters": clusters_sorted[: int(args.top_k)],
    }


# ── Phase 3 of the predictive epic: forecaster tool ───────────────────────


class PredictLaneArgs(BaseModel):
    commodity_hs: str = Field(description="HS code, e.g. '30771' or '100630'.")
    destination_m49: int = Field(description="UN M49 code for the destination country.")
    origin_m49: int = Field(description="UN M49 code for the origin country.")


@tool(
    description=(
        "Predict the next-period Composite Vulnerability Score (CVS) for a "
        "lane using the production forecaster (pooled LightGBM with quantile "
        "intervals). Returns target_period, cvs_point, cvs_low, cvs_high "
        "(80% interval), direction, confidence, and the top drivers from the "
        "trained model. Returns {ok: false, predictive_unavailable: true} "
        "when the forecaster was not trained at startup."
    )
)
def predict_lane_next_period(
    args: PredictLaneArgs, *, state: Any
) -> dict[str, Any]:
    """Wrap the production forecaster for the agent + HTTP endpoint.

    Reads the lane's full scored history up to the latest populated period,
    builds the causal feature vector, and asks ``state.forecaster`` to
    predict the next period.
    """
    forecaster = getattr(state, "forecaster", None)
    if forecaster is None:
        return {
            "ok": False,
            "predictive_unavailable": True,
            "reason": (
                "Forecaster was not trained at startup (no scored_history, "
                "lightgbm install missing, or training failed). "
                "Run `python -m script.predictive coverage` on the server."
            ),
        }

    from defensefood.agent.predictive import extract_corridor_features
    from defensefood.agent.predictive.forecaster import ForecastInput

    history = getattr(state, "scored_history", None) or {}
    populated = sorted(
        int(p) for p, snap in history.items() if isinstance(snap, dict) and snap
    )
    if not populated:
        return {
            "ok": False,
            "predictive_unavailable": True,
            "reason": "Empty scored_history.",
        }

    lane_key = (
        str(args.commodity_hs),
        int(args.destination_m49),
        int(args.origin_m49),
    )
    seq: list = []
    for p in populated:
        snap = history.get(p) or {}
        if lane_key not in snap:
            continue
        fv = extract_corridor_features(
            state,
            commodity_hs=lane_key[0],
            destination_m49=lane_key[1],
            origin_m49=lane_key[2],
            period=p,
        )
        if fv is not None:
            seq.append(fv)
    if not seq:
        return {
            "ok": False,
            "no_history": True,
            "reason": f"No scored history for lane {lane_key}.",
        }

    as_of = int(seq[-1].period)
    query = ForecastInput(
        commodity_hs=lane_key[0],
        destination_m49=lane_key[1],
        origin_m49=lane_key[2],
        as_of_period=as_of,
        history=seq,
    )
    out = forecaster.predict(query)

    last = seq[-1]
    return {
        "ok": True,
        "as_of_period": as_of,
        "target_period": int(out.target_period),
        "cvs_point": out.cvs_point,
        "cvs_low": out.cvs_low,
        "cvs_high": out.cvs_high,
        "his_point": out.his_point,
        "direction": out.direction,
        "confidence": out.confidence,
        "drivers": list(out.drivers or []),
        "notes": list(out.notes or []),
        "observed": {
            "period": last.period,
            "cvs": last.cvs,
            "his": last.his,
            "notification_count": last.notification_count,
        },
    }


__all__ = [
    "TOOL_REGISTRY",
    "ToolSpec",
    "tool",
    "invoke_tool",
    "anthropic_schemas",
    "openai_schemas",
]
