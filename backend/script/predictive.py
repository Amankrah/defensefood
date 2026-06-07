"""
Predictive subsystem CLI — Phase 1.

Subcommands:

    python -m script.predictive backtest [--forecaster persistence|chapter_median]
        Walk-forward back-test on state.scored_history. Writes a JSON +
        CSV report under ``script/output/predictive_eval_YYYYMMDD.{json,csv}``
        and prints a summary table. Both forecasters are run by default.

    python -m script.predictive predict <hs> <dest> <origin>
        One-shot prediction for one lane using a chosen forecaster.

    python -m script.predictive history <hs> <dest> <origin>
        Print the per-period scored history for one lane.

    python -m script.predictive coverage
        Sanity check: lists every populated period and the count of
        scored lanes per period.

Output is human-readable by default; pass ``--json`` for machine-readable
JSON. Mirrors the conventions established in ``script/eval_agent.py`` and
``script/agent_admin.py``.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("predictive")

OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# Forecaster names supported by the CLI. The factory in
# ``defensefood.agent.predictive.baselines`` is the source of truth.
ALL_FORECASTER_NAMES = (
    "persistence",
    "chapter_median",
    "lightgbm",
    "lightgbm_lite",
)


# ── helpers ──────────────────────────────────────────────────────────────


def _fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "—"
    return f"{x * 100:.1f}%"


def _fmt_num(x: Optional[float], digits: int = 4) -> str:
    if x is None:
        return "—"
    return f"{x:.{digits}f}"


def _print_table(headers: list[str], rows: list[list[Any]]) -> None:
    if not rows:
        print("(no rows)")
        return
    widths = [
        max(len(str(h)), *(len(str(r[i])) for r in rows))
        for i, h in enumerate(headers)
    ]
    sep = "  "
    print(sep.join(str(h).ljust(widths[i]) for i, h in enumerate(headers)))
    print(sep.join("─" * widths[i] for i in range(len(headers))))
    for r in rows:
        print(sep.join(str(c).ljust(widths[i]) for i, c in enumerate(r)))


def _bootstrap_state() -> Any:
    """Build the production AppState (lazy load + corpus indices)."""
    from defensefood.api.dependencies import get_state

    return get_state()


def _walk_summary_row(name: str, walk: Any) -> list[Any]:
    return [
        name,
        walk.target_period,
        walk.n_cases,
        walk.n_with_label,
        _fmt_num(walk.mae),
        _fmt_num(walk.rmse),
        _fmt_pct(walk.direction_accuracy),
        _fmt_pct(walk.interval_coverage),
    ]


def _aggregate(walks: list[Any]) -> dict[str, Any]:
    """Cross-walk averages weighted by n_with_label."""
    import math

    total_n = sum(w.n_with_label or 0 for w in walks)
    weighted_mae = 0.0
    weighted_sq = 0.0
    dir_hits = 0
    dir_total = 0
    int_hits = 0
    int_total = 0
    for w in walks:
        n = w.n_with_label or 0
        if w.mae is not None and n:
            weighted_mae += float(w.mae) * n
        if w.rmse is not None and n:
            weighted_sq += float(w.rmse) ** 2 * n
        if w.direction_accuracy is not None and n:
            dir_hits += int(round(w.direction_accuracy * n))
            dir_total += n
        if w.interval_coverage is not None and n:
            int_hits += int(round(w.interval_coverage * n))
            int_total += n
    return {
        "n_cases": sum(w.n_cases for w in walks),
        "n_with_label": total_n,
        "mae": (weighted_mae / total_n) if total_n else None,
        "rmse": math.sqrt(weighted_sq / total_n) if total_n else None,
        "direction_accuracy": (dir_hits / dir_total) if dir_total else None,
        "interval_coverage": (int_hits / int_total) if int_total else None,
    }


def _write_reports(
    payload: dict[str, Any], *, prefix: str = "predictive_eval"
) -> tuple[Path, Path]:
    """Write JSON + CSV under OUTPUT_DIR with the YYYYMMDD suffix."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat().replace("-", "")
    json_path = OUTPUT_DIR / f"{prefix}_{today}.json"
    csv_path = OUTPUT_DIR / f"{prefix}_{today}.csv"

    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    # CSV is per-walk; aggregates appear as additional rows with target_period="*".
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "forecaster",
                "target_period",
                "n_cases",
                "n_with_label",
                "mae",
                "rmse",
                "direction_accuracy",
                "interval_coverage",
            ]
        )
        for name, blob in payload.get("forecasters", {}).items():
            for walk in blob.get("walks", []):
                w.writerow(
                    [
                        name,
                        walk["target_period"],
                        walk["n_cases"],
                        walk["n_with_label"],
                        _fmt_num(walk.get("mae")),
                        _fmt_num(walk.get("rmse")),
                        _fmt_num(walk.get("direction_accuracy")),
                        _fmt_num(walk.get("interval_coverage")),
                    ]
                )
            agg = blob.get("aggregate", {})
            w.writerow(
                [
                    name,
                    "*",
                    agg.get("n_cases"),
                    agg.get("n_with_label"),
                    _fmt_num(agg.get("mae")),
                    _fmt_num(agg.get("rmse")),
                    _fmt_num(agg.get("direction_accuracy")),
                    _fmt_num(agg.get("interval_coverage")),
                ]
            )

    return json_path, csv_path


# ── subcommand: backtest ─────────────────────────────────────────────────


def cmd_backtest(args: argparse.Namespace) -> int:
    from defensefood.agent.predictive import build_forecaster, walk_forward

    forecasters = (
        [args.forecaster] if args.forecaster else list(ALL_FORECASTER_NAMES)
    )

    logger.info("Building corpus state...")
    state = _bootstrap_state()
    logger.info("State ready; running back-test on %d forecaster(s)", len(forecasters))

    forecaster_payloads: dict[str, Any] = {}
    for name in forecasters:

        def _factory(_name: str = name) -> Any:
            return build_forecaster(_name, state=state)

        walks = walk_forward(state, forecaster_factory=_factory)
        walk_payload = []
        for w in walks:
            walk_payload.append(
                {
                    "target_period": w.target_period,
                    "train_periods": w.train_periods,
                    "n_cases": w.n_cases,
                    "n_with_label": w.n_with_label,
                    "mae": w.mae,
                    "rmse": w.rmse,
                    "direction_accuracy": w.direction_accuracy,
                    "interval_coverage": w.interval_coverage,
                    "notes": w.notes,
                }
            )
        forecaster_payloads[name] = {
            "walks": walk_payload,
            "aggregate": _aggregate(walks),
        }

    payload = {
        "generated_at": date.today().isoformat(),
        "target_metric": args.target,
        "forecasters": forecaster_payloads,
    }

    if args.json:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, default=str)
        return 0

    rows: list[list[Any]] = []
    for name, blob in forecaster_payloads.items():
        for walk in blob.get("walks", []):
            rows.append(
                [
                    name,
                    walk["target_period"],
                    walk["n_cases"],
                    walk["n_with_label"],
                    _fmt_num(walk.get("mae")),
                    _fmt_num(walk.get("rmse")),
                    _fmt_pct(walk.get("direction_accuracy")),
                    _fmt_pct(walk.get("interval_coverage")),
                ]
            )
        agg = blob.get("aggregate", {})
        rows.append(
            [
                f"{name} (agg)",
                "*",
                agg.get("n_cases") or 0,
                agg.get("n_with_label") or 0,
                _fmt_num(agg.get("mae")),
                _fmt_num(agg.get("rmse")),
                _fmt_pct(agg.get("direction_accuracy")),
                _fmt_pct(agg.get("interval_coverage")),
            ]
        )

    print(f"\nWalk-forward back-test (target={args.target}):")
    _print_table(
        [
            "forecaster",
            "target_period",
            "n_cases",
            "n_with_label",
            "mae",
            "rmse",
            "direction_acc",
            "interval_cov",
        ],
        rows,
    )

    json_path, csv_path = _write_reports(payload)
    print(f"\nWrote {json_path}")
    print(f"Wrote {csv_path}")
    return 0


# ── subcommand: predict ──────────────────────────────────────────────────


def cmd_predict(args: argparse.Namespace) -> int:
    from defensefood.agent.predictive import build_forecaster
    from defensefood.agent.predictive.eval_harness import _build_history_up_to
    from defensefood.agent.predictive.forecaster import ForecastInput

    state = _bootstrap_state()
    lane_key = (args.hs, int(args.dest), int(args.origin))

    history = getattr(state, "scored_history", None) or {}
    populated = sorted(int(p) for p, snap in history.items() if snap)
    if not populated:
        print("error: scored_history is empty.", file=sys.stderr)
        return 1
    as_of = populated[-1]
    seq = _build_history_up_to(state, lane_key, as_of)
    if not seq:
        print(
            f"error: no scored history for lane {lane_key} at any period ≤ {as_of}.",
            file=sys.stderr,
        )
        return 1

    forecaster = build_forecaster(args.forecaster, state=state)
    query = ForecastInput(
        commodity_hs=lane_key[0],
        destination_m49=lane_key[1],
        origin_m49=lane_key[2],
        as_of_period=int(seq[-1].period),
        history=seq,
    )
    out = forecaster.predict(query)

    if args.json:
        json.dump(asdict(out), sys.stdout, ensure_ascii=False, indent=2, default=str)
        return 0

    last = seq[-1]
    print(f"\nLane: {lane_key[0]} / {lane_key[1]} / {lane_key[2]}")
    print(f"  last observed period : {last.period}  (cvs = {_fmt_num(last.cvs)})")
    print(f"  forecaster           : {args.forecaster}")
    print(f"  target period        : {out.target_period}")
    print(f"  cvs_point            : {_fmt_num(out.cvs_point)}")
    if out.cvs_low is not None and out.cvs_high is not None:
        print(f"  80% interval         : [{_fmt_num(out.cvs_low)}, {_fmt_num(out.cvs_high)}]")
    print(f"  direction            : {out.direction}")
    print(f"  confidence           : {out.confidence}")
    if out.drivers:
        print(f"  drivers              : {', '.join(out.drivers)}")
    if out.notes:
        print(f"  notes                : {', '.join(out.notes)}")
    return 0


# ── subcommand: history ──────────────────────────────────────────────────


def cmd_history(args: argparse.Namespace) -> int:
    from defensefood.agent.predictive import lane_history

    state = _bootstrap_state()
    history = lane_history(
        state.scored_history, (args.hs, int(args.dest), int(args.origin))
    )

    if args.json:
        json.dump(history, sys.stdout, ensure_ascii=False, indent=2, default=str)
        return 0

    if not history:
        print(
            f"(no history for lane {args.hs} / {args.dest} / {args.origin})"
        )
        return 0

    print(
        f"\nHistory for lane {args.hs} / {args.dest} / {args.origin}:"
    )
    _print_table(
        ["period", "cvs", "cvs_mode", "his", "sci", "ocs", "notifs"],
        [
            [
                row.get("period"),
                _fmt_num(row.get("cvs")),
                row.get("cvs_mode") or "—",
                _fmt_num(row.get("his")),
                _fmt_num(row.get("sci"), 3),
                _fmt_num(row.get("ocs"), 3),
                row.get("notification_count") or 0,
            ]
            for row in history
        ],
    )
    return 0


# ── subcommand: cliff ────────────────────────────────────────────────────


def cmd_cliff(args: argparse.Namespace) -> int:
    """Surface the lanes with the largest absolute CVS deltas between
    ``period - 1`` and ``period``.

    Built to investigate the 2026-06-07 backtest result where every
    forecaster degraded sharply at 2023 (persistence MAE jumped from
    0.012-0.020 to 0.040, direction accuracy collapsed to 51%).

    If the chapter-median baseline is stable across years but per-lane
    metrics shift dramatically in one year, the drift is per-lane — likely
    a hazard-side event (new RASFF notifications on a subset of lanes)
    rather than a corpus-wide structural change.
    """
    state = _bootstrap_state()
    history = getattr(state, "scored_history", None) or {}
    populated = sorted(
        int(p) for p, snap in history.items() if isinstance(snap, dict) and snap
    )
    if not populated:
        print("error: scored_history is empty.", file=sys.stderr)
        return 1

    target = int(args.period) if args.period else populated[-1]
    if target not in populated:
        print(
            f"error: period {target} has no entries. "
            f"Populated: {populated}",
            file=sys.stderr,
        )
        return 1
    prior_candidates = [p for p in populated if p < target]
    if not prior_candidates:
        print(
            f"error: period {target} is the earliest in history; no delta possible.",
            file=sys.stderr,
        )
        return 1
    prior = prior_candidates[-1]

    target_snap = history[target]
    prior_snap = history[prior]

    movers: list[dict[str, Any]] = []
    for lane_key, target_entry in target_snap.items():
        prior_entry = prior_snap.get(lane_key)
        if prior_entry is None:
            continue
        try:
            cvs_t = float(target_entry.get("cvs"))
            cvs_p = float(prior_entry.get("cvs"))
        except (TypeError, ValueError):
            continue
        delta = cvs_t - cvs_p
        # Component deltas to help diagnose which side moved.
        his_t = target_entry.get("his")
        his_p = prior_entry.get("his")
        try:
            his_delta = float(his_t) - float(his_p)
        except (TypeError, ValueError):
            his_delta = None
        try:
            sci_delta = float(target_entry.get("sci")) - float(prior_entry.get("sci"))
        except (TypeError, ValueError):
            sci_delta = None
        notif_delta = (
            int(target_entry.get("notification_count") or 0)
            - int(prior_entry.get("notification_count") or 0)
        )
        movers.append(
            {
                "lane_key": "/".join(str(x) for x in lane_key),
                "commodity_name": (
                    target_entry.get("commodity_name") or ""
                )[:30],
                "origin_country": target_entry.get("origin_country") or "",
                "destination_country": target_entry.get("destination_country") or "",
                "cvs_prior": cvs_p,
                "cvs_target": cvs_t,
                "cvs_delta": delta,
                "his_delta": his_delta,
                "sci_delta": sci_delta,
                "notif_delta": notif_delta,
                "cvs_mode": target_entry.get("cvs_mode"),
            }
        )

    movers.sort(key=lambda m: abs(m["cvs_delta"]), reverse=True)
    top = movers[: int(args.top_k)]

    if args.json:
        json.dump(
            {
                "prior_period": prior,
                "target_period": target,
                "n_lanes_compared": len(movers),
                "top_movers": top,
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        return 0

    # Aggregate stats first.
    abs_deltas = [abs(m["cvs_delta"]) for m in movers]
    abs_deltas.sort()
    median_abs_delta = (
        abs_deltas[len(abs_deltas) // 2] if abs_deltas else 0.0
    )
    p90_abs_delta = (
        abs_deltas[int(0.9 * len(abs_deltas))] if abs_deltas else 0.0
    )
    rising = sum(1 for m in movers if m["cvs_delta"] > 0.03)
    falling = sum(1 for m in movers if m["cvs_delta"] < -0.03)
    stable = len(movers) - rising - falling

    print(
        f"\nCVS delta distribution {prior} → {target} "
        f"({len(movers)} lanes compared):"
    )
    print(f"  median |Δ|         : {median_abs_delta:.4f}")
    print(f"  90th pct |Δ|       : {p90_abs_delta:.4f}")
    print(f"  rising  (Δ > 0.03) : {rising}")
    print(f"  falling (Δ <-0.03) : {falling}")
    print(f"  stable             : {stable}")

    print(f"\nTop {len(top)} movers by |Δ CVS|:")
    _print_table(
        [
            "lane",
            "commodity",
            "origin → dest",
            "cvs_t-1",
            "cvs_t",
            "Δ cvs",
            "Δ his",
            "Δ sci",
            "Δ notifs",
            "mode",
        ],
        [
            [
                m["lane_key"],
                m["commodity_name"],
                f"{m['origin_country'][:12]} → {m['destination_country'][:12]}",
                _fmt_num(m["cvs_prior"], 3),
                _fmt_num(m["cvs_target"], 3),
                f"{m['cvs_delta']:+.3f}",
                _fmt_num(m["his_delta"], 3) if m["his_delta"] is not None else "—",
                _fmt_num(m["sci_delta"], 3) if m["sci_delta"] is not None else "—",
                f"{m['notif_delta']:+d}",
                m["cvs_mode"] or "—",
            ]
            for m in top
        ],
    )
    return 0


# ── subcommand: coverage ─────────────────────────────────────────────────


def cmd_coverage(args: argparse.Namespace) -> int:
    from defensefood.agent.predictive import coverage_summary

    state = _bootstrap_state()
    summary = coverage_summary(state.scored_history)

    if args.json:
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, default=str)
        return 0

    print(
        f"\nScored history coverage ({len(summary['periods'])} periods, "
        f"{summary['total_lane_periods']} lane-periods):"
    )
    _print_table(
        ["period", "corridors", "with_cvs", "cvs_coverage"],
        [
            [r["period"], r["corridors"], r["with_cvs"], _fmt_pct(r["cvs_coverage"])]
            for r in summary["by_period"]
        ],
    )
    return 0


# ── argparse wiring ──────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="predictive",
        description=(
            "Predictive subsystem CLI. Runs walk-forward back-tests, "
            "one-shot lane forecasts, and per-lane history dumps against "
            "state.scored_history."
        ),
    )

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json",
        action="store_true",
        dest="json",
        help="Emit machine-readable JSON instead of pretty tables.",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    bt = sub.add_parser(
        "backtest",
        parents=[common],
        help="Walk-forward back-test of one or all baseline forecasters.",
    )
    bt.add_argument(
        "--forecaster",
        choices=ALL_FORECASTER_NAMES,
        default=None,
        help="Run a single forecaster (default: all).",
    )
    bt.add_argument(
        "--target",
        default="cvs",
        choices=["cvs"],
        help="Target metric for the back-test (Phase 1 supports CVS only).",
    )
    bt.set_defaults(handler=cmd_backtest)

    pr = sub.add_parser(
        "predict",
        parents=[common],
        help="One-shot prediction for one lane.",
    )
    pr.add_argument("hs")
    pr.add_argument("dest", type=int)
    pr.add_argument("origin", type=int)
    pr.add_argument(
        "--forecaster",
        choices=ALL_FORECASTER_NAMES,
        default="persistence",
    )
    pr.set_defaults(handler=cmd_predict)

    hi = sub.add_parser(
        "history",
        parents=[common],
        help="Print per-period scored history for one lane.",
    )
    hi.add_argument("hs")
    hi.add_argument("dest", type=int)
    hi.add_argument("origin", type=int)
    hi.set_defaults(handler=cmd_history)

    cov = sub.add_parser(
        "coverage",
        parents=[common],
        help="Sanity check: counts per period in scored_history.",
    )
    cov.set_defaults(handler=cmd_coverage)

    cl = sub.add_parser(
        "cliff",
        parents=[common],
        help=(
            "Surface the lanes with the largest absolute CVS deltas "
            "between (period - 1) and ``period`` (defaults to latest)."
        ),
    )
    cl.add_argument(
        "--period",
        type=int,
        default=None,
        help="Target period; default is the latest populated period.",
    )
    cl.add_argument("--top-k", dest="top_k", type=int, default=10)
    cl.set_defaults(handler=cmd_cliff)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(message)s"
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "json"):
        args.json = False
    try:
        return args.handler(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        if os.environ.get("PREDICTIVE_TRACEBACK"):
            raise
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
