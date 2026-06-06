"""
Agent subsystem admin CLI (Phase 6 — CLI-only).

Replaces the previously-shipped HTTP admin endpoints. Operates directly on
the SQLite cache at ``backend/data/agent.db`` so there is no network surface
and no auth layer to misconfigure.

Subcommands:

    python -m script.agent_admin stats [--days 7]
        Cost ledger window + brief inventory + lifetime totals.

    python -m script.agent_admin briefs [--use-case lane_brief] [--limit 50]
        Recent briefs (header only).

    python -m script.agent_admin audit <brief_id>
        Full audit trail for one brief: payload + audit log rows.

    python -m script.agent_admin verifier-notes [--limit 30]
        Recent verifier_notes across all briefs.

    python -m script.agent_admin invalidate {--use-case U | --target-key K | both}
        Delete cached brief rows matching the filter. Refuses if both
        filters are omitted (would wipe the whole cache).

    python -m script.agent_admin methodology [--prompts | --tools]
        List the registered tools and / or print the system prompt files.
        Read-only.

    python -m script.agent_admin conversations [--limit 20]
        List recent Q&A conversation headers.

JSON-friendly output for piping:

    python -m script.agent_admin stats --json | jq .totals
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("agent_admin")


def _fmt_usd(v: float) -> str:
    return f"${v:.4f}"


def _fmt_secs_from_ms(ms: float) -> str:
    return f"{ms/1000:.1f}s"


def _fmt_when(epoch: Optional[float]) -> str:
    if epoch is None:
        return "—"
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")


def _print_table(headers: list[str], rows: list[list[Any]]) -> None:
    """Tiny stdout table printer.

    Always uses the current ``sys.stdout`` (resolved at call time, not at
    def time) so it cooperates with ``contextlib.redirect_stdout`` in tests.
    """
    if not rows:
        print("(no rows)")
        return
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    sep = "  "
    print(sep.join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print(sep.join("─" * widths[i] for i in range(len(headers))))
    for r in rows:
        print(sep.join(str(c).ljust(widths[i]) for i, c in enumerate(r)))


# ── subcommand handlers ───────────────────────────────────────────────────


def cmd_stats(args: argparse.Namespace) -> int:
    from defensefood.agent import cache as agent_cache

    inv = agent_cache.brief_inventory()
    ledger = agent_cache.cost_ledger_window(days=args.days)
    by_day_total: dict[str, float] = {}
    by_use_case_total: dict[str, float] = {}
    for row in ledger:
        d = str(row.get("day"))
        uc = str(row.get("use_case"))
        usd = float(row.get("usd") or 0.0)
        by_day_total[d] = by_day_total.get(d, 0.0) + usd
        by_use_case_total[uc] = by_use_case_total.get(uc, 0.0) + usd

    total_briefs = sum(int(r.get("n") or 0) for r in inv)
    total_cost = sum(float(r.get("total_cost_usd") or 0.0) for r in inv)

    if args.json:
        json.dump(
            {
                "totals": {
                    "briefs": total_briefs,
                    "lifetime_cost_usd": round(total_cost, 4),
                    "use_cases": len(inv),
                },
                "brief_inventory": inv,
                "cost_window_days": args.days,
                "cost_ledger": ledger,
                "cost_by_day": [
                    {"day": d, "usd": round(v, 4)}
                    for d, v in sorted(by_day_total.items())
                ],
                "cost_by_use_case": [
                    {"use_case": k, "usd": round(v, 4)}
                    for k, v in sorted(by_use_case_total.items(), key=lambda x: -x[1])
                ],
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        return 0

    # Human output.
    print(f"\nTotals (lifetime):")
    print(f"  briefs        : {total_briefs}")
    print(f"  cost          : {_fmt_usd(total_cost)}")
    print(f"  use cases     : {len(inv)}")

    print(f"\nBrief inventory by use case:")
    _print_table(
        ["use_case", "n", "total_cost_usd", "mean_latency", "last"],
        [
            [
                r["use_case"],
                r["n"],
                _fmt_usd(r["total_cost_usd"]),
                _fmt_secs_from_ms(r["mean_latency_ms"]),
                _fmt_when(r["last_at"]),
            ]
            for r in inv
        ],
    )

    print(f"\nCost ledger (last {args.days} days):")
    _print_table(
        ["day", "use_case", "provider", "model", "tokens_in", "tokens_out", "usd"],
        [
            [
                r["day"],
                r["use_case"],
                r["provider"],
                r["model"],
                r["tokens_in"],
                r["tokens_out"],
                _fmt_usd(r["usd"]),
            ]
            for r in ledger
        ],
    )
    return 0


def cmd_briefs(args: argparse.Namespace) -> int:
    from defensefood.agent import cache as agent_cache

    rows = agent_cache.list_briefs(
        use_case=args.use_case, limit=args.limit
    )
    if args.json:
        json.dump(rows, sys.stdout, ensure_ascii=False, indent=2, default=str)
        return 0
    print(
        f"\nRecent briefs"
        + (f" (use_case={args.use_case})" if args.use_case else "")
        + f", limit {args.limit}:"
    )
    _print_table(
        ["id", "use_case", "target_key", "latency", "cost", "when"],
        [
            [
                r["id"],
                r["use_case"],
                r["target_key"],
                _fmt_secs_from_ms(r["latency_ms"]),
                _fmt_usd(r["cost_usd"]),
                _fmt_when(r["created_at"]),
            ]
            for r in rows
        ],
    )
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    from defensefood.agent import cache as agent_cache

    full = agent_cache.get_brief_full(args.brief_id)
    if full is None:
        print(f"error: brief id {args.brief_id} not found.", file=sys.stderr)
        return 1
    audit = agent_cache.get_audit(args.brief_id)

    if args.json:
        json.dump(
            {**full, "audit": audit},
            sys.stdout,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        return 0

    print(f"\nBrief #{full['id']}  ({full['use_case']} / {full['target_key']})")
    print(f"  provider/model : {full['provider']} / {full['model']}")
    print(f"  latency        : {_fmt_secs_from_ms(full['latency_ms'])}")
    print(f"  cost           : {_fmt_usd(full['cost_usd'])}")
    print(f"  created        : {_fmt_when(full['created_at'])}")
    print(f"  snapshot       : {full['snapshot_hash']}")

    print(f"\nBrief payload:")
    print(json.dumps(full["brief"], ensure_ascii=False, indent=2, default=str))

    print(f"\nAudit log ({len(audit)} row(s)):")
    for row in audit:
        print(f"\n  ── row #{row['id']}  role={row['role']}  at={_fmt_when(row['created_at'])}")
        if row.get("tokens_in") is not None:
            print(
                f"     tokens: {row['tokens_in']} → {row.get('tokens_out') or 0}"
            )
        if row.get("tool_calls"):
            print(f"     tool calls: {len(row['tool_calls'])}")
            for i, t in enumerate(row["tool_calls"][:20], start=1):
                print(
                    f"       {i:02d}. {t.get('name', '?')} · "
                    f"{t.get('latency_ms', 0)}ms"
                )
        # Truncated content preview.
        content_preview = json.dumps(
            row.get("content"), ensure_ascii=False, indent=2, default=str
        )
        if len(content_preview) > 600:
            content_preview = content_preview[:600] + "\n... (truncated)"
        for line in content_preview.splitlines():
            print(f"     | {line}")
    return 0


def cmd_verifier_notes(args: argparse.Namespace) -> int:
    from defensefood.agent import cache as agent_cache

    rows = agent_cache.recent_verifier_notes(limit=args.limit)
    if args.json:
        json.dump(rows, sys.stdout, ensure_ascii=False, indent=2, default=str)
        return 0
    print(f"\nRecent verifier notes (limit {args.limit}):")
    for r in rows:
        print(
            f"\n  brief #{r.get('brief_id') or '?'}  "
            f"[{r['use_case']}]  {r.get('target_key') or ''}  "
            f"@ {_fmt_when(r['created_at'])}"
        )
        for n in r["notes"]:
            print(f"    · {n}")
    if not rows:
        print("(no rows)")
    return 0


def cmd_invalidate(args: argparse.Namespace) -> int:
    from defensefood.agent import cache as agent_cache

    if not args.use_case and not args.target_key:
        print(
            "error: provide --use-case and/or --target-key. Refusing to wipe "
            "the whole cache.",
            file=sys.stderr,
        )
        return 2
    if not args.yes:
        label = (
            f"use_case={args.use_case!r}" if args.use_case else ""
        ) + (
            f" target_key={args.target_key!r}" if args.target_key else ""
        )
        confirm = input(
            f"About to invalidate cached briefs matching {label.strip()}.\n"
            "Type 'yes' to confirm: "
        ).strip().lower()
        if confirm != "yes":
            print("aborted.")
            return 1

    n = agent_cache.invalidate_brief_cache(
        use_case=args.use_case, target_key=args.target_key
    )
    print(f"deleted {n} row(s).")
    return 0


def cmd_methodology(args: argparse.Namespace) -> int:
    # IMPORT TRIGGERS REGISTRATION: importing the briefs modules wires up
    # every submit_* tool into the registry so the listing is complete.
    from defensefood.agent.briefs import (  # noqa: F401
        anomaly_explainer,
        country_brief,
        hypotheses,
        lane_brief,
        period_shift,
    )
    from defensefood.agent.qa import runner as _qa_runner  # noqa: F401
    from defensefood.agent.tools import TOOL_REGISTRY
    from defensefood.agent.config import get_config

    show_tools = args.tools or not args.prompts
    show_prompts = args.prompts or not args.tools

    if args.json:
        payload: dict[str, Any] = {}
        if show_tools:
            payload["tools"] = [
                {
                    "name": name,
                    "description": spec.description,
                    "args_model": spec.args_model.__name__,
                    "json_schema": spec.json_schema(),
                }
                for name, spec in sorted(TOOL_REGISTRY.items())
            ]
        if show_prompts:
            cfg = get_config()
            backend_root = Path(__file__).resolve().parents[1]
            prompts_dir = backend_root / cfg.prompts_dir
            prompts_payload = []
            if prompts_dir.exists():
                for p in sorted(prompts_dir.glob("*.md")):
                    prompts_payload.append(
                        {
                            "name": p.stem,
                            "filename": p.name,
                            "content": p.read_text(encoding="utf-8"),
                        }
                    )
            payload["prompts"] = prompts_payload
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        return 0

    if show_tools:
        print(f"\nTool registry ({len(TOOL_REGISTRY)} tools):")
        for name, spec in sorted(TOOL_REGISTRY.items()):
            print(f"\n  {name}")
            print(f"    args  : {spec.args_model.__name__}")
            print(f"    desc  : {spec.description}")

    if show_prompts:
        cfg = get_config()
        backend_root = Path(__file__).resolve().parents[1]
        prompts_dir = backend_root / cfg.prompts_dir
        if not prompts_dir.exists():
            print(f"\n(prompts dir not found: {prompts_dir})")
            return 1
        files = sorted(prompts_dir.glob("*.md"))
        print(f"\nSystem prompts ({len(files)} file(s) in {prompts_dir}):")
        for p in files:
            print(f"  - {p.name}  ({p.stat().st_size} bytes)")
        if args.full:
            for p in files:
                print(f"\n──── {p.name} ────")
                print(p.read_text(encoding="utf-8"))
    return 0


def cmd_conversations(args: argparse.Namespace) -> int:
    from defensefood.agent import cache as agent_cache

    rows = agent_cache.list_conversations(limit=args.limit)
    if args.json:
        json.dump(rows, sys.stdout, ensure_ascii=False, indent=2, default=str)
        return 0
    print(f"\nRecent conversations (limit {args.limit}):")
    _print_table(
        ["id", "messages", "started", "last_used", "title"],
        [
            [
                r["id"][:12] + "…",
                r["message_count"],
                _fmt_when(r["started_at"]),
                _fmt_when(r["last_used_at"]),
                (r.get("title") or "")[:40],
            ]
            for r in rows
        ],
    )
    return 0


# ── argparse wiring ───────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent_admin",
        description=(
            "Admin CLI for the agent subsystem. Operates directly on the "
            "SQLite cache at backend/data/agent.db; no HTTP, no auth."
        ),
    )
    # Common ``--json`` flag available BEFORE the subcommand. Each
    # subcommand also exposes it via a parent parser so users can write
    # ``agent_admin stats --json`` (the more natural form).
    p.add_argument(
        "--json",
        action="store_true",
        dest="json",
        help="Emit machine-readable JSON instead of pretty tables.",
    )

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json",
        action="store_true",
        dest="json",
        help="Emit machine-readable JSON instead of pretty tables.",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("stats", parents=[common], help="Cost ledger + brief inventory.")
    s.add_argument("--days", type=int, default=7)
    s.set_defaults(handler=cmd_stats)

    b = sub.add_parser("briefs", parents=[common], help="Recent briefs.")
    b.add_argument("--use-case", dest="use_case", default=None)
    b.add_argument("--limit", type=int, default=50)
    b.set_defaults(handler=cmd_briefs)

    au = sub.add_parser("audit", parents=[common], help="Audit trail for one brief.")
    au.add_argument("brief_id", type=int)
    au.set_defaults(handler=cmd_audit)

    vn = sub.add_parser("verifier-notes", parents=[common], help="Recent verifier notes.")
    vn.add_argument("--limit", type=int, default=30)
    vn.set_defaults(handler=cmd_verifier_notes)

    inv = sub.add_parser("invalidate", parents=[common], help="Delete cached brief rows.")
    inv.add_argument("--use-case", dest="use_case", default=None)
    inv.add_argument("--target-key", dest="target_key", default=None)
    inv.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    inv.set_defaults(handler=cmd_invalidate)

    me = sub.add_parser("methodology", parents=[common], help="List tools and / or prompts.")
    me.add_argument("--tools", action="store_true", help="Show only the tool registry.")
    me.add_argument("--prompts", action="store_true", help="Show only the prompts.")
    me.add_argument("--full", action="store_true", help="Print full prompt content.")
    me.set_defaults(handler=cmd_methodology)

    co = sub.add_parser("conversations", parents=[common], help="Recent Q&A conversation headers.")
    co.add_argument("--limit", type=int, default=20)
    co.set_defaults(handler=cmd_conversations)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(message)s"
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    # Propagate the global --json down to the subcommand handler.
    if not hasattr(args, "json"):
        args.json = False
    try:
        return args.handler(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        if os.environ.get("AGENT_ADMIN_TRACEBACK"):
            raise
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
