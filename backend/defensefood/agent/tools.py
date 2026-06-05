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
    except Exception as exc:  # noqa: BLE001 — broad on purpose; surface to LLM
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
    from defensefood.api.routers.corridors import (
        get_corridor_trade_anomalies as _impl,
    )

    return _impl(args.commodity_hs, args.destination_m49, args.origin_m49, state=state)


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


__all__ = [
    "TOOL_REGISTRY",
    "ToolSpec",
    "tool",
    "invoke_tool",
    "anthropic_schemas",
    "openai_schemas",
]
