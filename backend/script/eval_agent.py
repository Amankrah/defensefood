"""
Phase 6.1 — agent evaluation harness.

Runs the agent subsystem against a golden set of corridors / countries /
period-shift comparisons / Q&A questions and emits a JSON + CSV report:

    script/output/agent_eval_YYYYMMDD.json
    script/output/agent_eval_YYYYMMDD.csv

Usage::

    python -m script.eval_agent             # full run, live API keys
    python -m script.eval_agent --dry-run   # validate plan only, no LLM calls
    python -m script.eval_agent --only lane_brief

The harness is intentionally lightweight: each case is a Python dict with
the use case key, target identifiers, and the assertions a passing case
must satisfy (required signal source_fields, required caveat markers,
maximum cost). The plan calls for ~50 lanes and ~15 countries; the
shipped set here is a small seed (5-7 cases per use case) that grows over
time as the corpus changes shape.

The harness deliberately does NOT seed conversation memory or change the
config; it runs as a normal client of the API surface, so any regression
in the production code paths surfaces here.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("eval_agent")

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


# ── case definitions ──────────────────────────────────────────────────────


@dataclass
class EvalCase:
    """One golden case the harness will run against the agent subsystem."""

    use_case: str
    target_key: str
    # Pretty label for the report.
    label: str
    # Source fields the brief MUST cite in key_signals (lane/country/period).
    required_signal_fields: list[str] = field(default_factory=list)
    # Caveat substrings the brief MUST inject (e.g. "informational", "sci_his").
    required_caveat_markers: list[str] = field(default_factory=list)
    # USD cap per case; harness flags when cost > this.
    max_cost_usd: float = 0.25
    # Optional: lanes-only fields used by the executor to call the generator.
    extra: dict[str, Any] = field(default_factory=dict)


# Seed cases. Grow these in follow-on PRs; today this is the smallest
# meaningful coverage spanning every use case + every CVS mode + the
# informational role.
GOLDEN_CASES: list[EvalCase] = [
    # Lane briefs — span cvs_modes and market presence.
    EvalCase(
        use_case="lane_brief",
        target_key="30771/250/724",
        label="Spain mussels into France (confirmed, sci_crs_his)",
        required_signal_fields=["cvs", "his"],
        max_cost_usd=0.05,
    ),
    EvalCase(
        use_case="lane_brief",
        target_key="100630/250/380",
        label="Italian rice into France (informational, sci_his)",
        required_signal_fields=["cvs", "his"],
        required_caveat_markers=["informational"],
        max_cost_usd=0.05,
    ),
    EvalCase(
        use_case="lane_brief",
        target_key="1006/528/586",
        label="Pakistani rice into Netherlands (re-export, IDR > 1)",
        required_signal_fields=["his", "idr"],
        required_caveat_markers=["idr"],
        max_cost_usd=0.05,
    ),
    # Country brief.
    EvalCase(
        use_case="country_brief",
        target_key="250",
        label="France (importer-heavy)",
        max_cost_usd=0.08,
    ),
    EvalCase(
        use_case="country_brief",
        target_key="380",
        label="Italy (importer + exporter)",
        max_cost_usd=0.08,
    ),
    # Period shift.
    EvalCase(
        use_case="period_shift",
        target_key="2022-2023",
        label="Corpus 2022 vs 2023",
        max_cost_usd=0.05,
        extra={"period_a": 2022, "period_b": 2023},
    ),
    # Hypotheses (Opus tier, higher cap).
    EvalCase(
        use_case="hypotheses",
        target_key="1006/528/586",
        label="Hypotheses for Pakistani rice into Netherlands",
        max_cost_usd=0.25,
    ),
    # Anomaly explainer.
    EvalCase(
        use_case="explain_anomaly",
        target_key="1006/528/586",
        label="Anomaly check on Pakistani rice into Netherlands",
        max_cost_usd=0.05,
    ),
]


# Q&A reference questions — separate set because they don't have a
# corridor target_key.
@dataclass
class QACase:
    """One reference Q&A: question + required intent + minimum-mention terms."""

    question: str
    required_intent: str
    required_in_scope: bool = True
    # Substrings the answer_markdown must contain (case-insensitive).
    required_mentions: list[str] = field(default_factory=list)
    max_cost_usd: float = 0.05


QA_CASES: list[QACase] = [
    QACase(
        question="What is Composite Vulnerability Score (CVS)?",
        required_intent="methodology",
        required_mentions=["CVS", "vulnerability"],
    ),
    QACase(
        question="Show corridors where CVS is in the top band.",
        required_intent="filter",
    ),
    QACase(
        question="Compare Spain and Italy as origins.",
        required_intent="compare",
        required_mentions=["Spain", "Italy"],
    ),
    QACase(
        question="What is the weather in Madrid?",
        required_intent="out_of_scope",
        required_in_scope=False,
        max_cost_usd=0.002,
    ),
]


# ── case execution ────────────────────────────────────────────────────────


@dataclass
class CaseResult:
    """Per-case outcome the report writes."""

    use_case: str
    target_key: str
    label: str
    passed: bool
    duration_ms: int
    cost_usd: float
    issues: list[str] = field(default_factory=list)
    model: str = ""
    provider: str = ""


def _signal_fields_from(brief: dict[str, Any]) -> set[str]:
    """Extract the set of source_field values across known schema shapes."""
    fields: set[str] = set()
    for key in ("key_signals", "supporting_signals", "signals"):
        sigs = brief.get(key)
        if isinstance(sigs, list):
            for s in sigs:
                if isinstance(s, dict):
                    sf = s.get("source_field")
                    if sf:
                        fields.add(str(sf))
    # Nested halves (country brief).
    for half_key in ("inbound", "outbound"):
        half = brief.get(half_key)
        if isinstance(half, dict):
            fields |= _signal_fields_from(half)
    return fields


def _caveats_from(brief: dict[str, Any]) -> list[str]:
    out: list[str] = []
    c = brief.get("caveats")
    if isinstance(c, list):
        out.extend(str(x) for x in c)
    return out


def _run_lane_brief(case: EvalCase, state: Any) -> CaseResult:
    from defensefood.agent.briefs.lane_brief import generate_lane_brief

    hs, dest, origin = case.target_key.split("/")
    t0 = time.perf_counter()
    issues: list[str] = []
    try:
        r = generate_lane_brief(
            hs, int(dest), int(origin), state=state, verify="fast"
        )
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            use_case=case.use_case,
            target_key=case.target_key,
            label=case.label,
            passed=False,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            cost_usd=0.0,
            issues=[f"raised: {type(exc).__name__}: {exc}"],
        )
    brief = r.brief.model_dump()
    fields = _signal_fields_from(brief)
    for req in case.required_signal_fields:
        if req not in fields:
            issues.append(f"missing required signal: {req}")
    caveats_text = "\n".join(_caveats_from(brief)).lower()
    for marker in case.required_caveat_markers:
        if marker.lower() not in caveats_text:
            issues.append(f"missing required caveat marker: {marker}")
    if r.cost_usd > case.max_cost_usd:
        issues.append(
            f"cost {r.cost_usd:.4f} exceeded cap {case.max_cost_usd:.4f}"
        )
    return CaseResult(
        use_case=case.use_case,
        target_key=case.target_key,
        label=case.label,
        passed=not issues,
        duration_ms=r.latency_ms,
        cost_usd=r.cost_usd,
        issues=issues,
        model=r.model,
        provider=r.provider,
    )


def _run_country_brief(case: EvalCase, state: Any) -> CaseResult:
    from defensefood.agent.briefs.country_brief import generate_country_brief

    t0 = time.perf_counter()
    issues: list[str] = []
    try:
        r = generate_country_brief(int(case.target_key), state=state, verify="fast")
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            use_case=case.use_case,
            target_key=case.target_key,
            label=case.label,
            passed=False,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            cost_usd=0.0,
            issues=[f"raised: {type(exc).__name__}: {exc}"],
        )
    if r.cost_usd > case.max_cost_usd:
        issues.append(
            f"cost {r.cost_usd:.4f} exceeded cap {case.max_cost_usd:.4f}"
        )
    return CaseResult(
        use_case=case.use_case,
        target_key=case.target_key,
        label=case.label,
        passed=not issues,
        duration_ms=r.latency_ms,
        cost_usd=r.cost_usd,
        issues=issues,
        model=r.model,
        provider=r.provider,
    )


def _run_period_shift(case: EvalCase, state: Any) -> CaseResult:
    from defensefood.agent.briefs.period_shift import generate_period_shift_brief

    t0 = time.perf_counter()
    issues: list[str] = []
    pa = int(case.extra.get("period_a") or 0) or None
    pb = int(case.extra.get("period_b") or 0) or None
    try:
        r = generate_period_shift_brief(
            state=state, period_a=pa, period_b=pb, verify="fast"
        )
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            use_case=case.use_case,
            target_key=case.target_key,
            label=case.label,
            passed=False,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            cost_usd=0.0,
            issues=[f"raised: {type(exc).__name__}: {exc}"],
        )
    if r.cost_usd > case.max_cost_usd:
        issues.append(
            f"cost {r.cost_usd:.4f} exceeded cap {case.max_cost_usd:.4f}"
        )
    return CaseResult(
        use_case=case.use_case,
        target_key=case.target_key,
        label=case.label,
        passed=not issues,
        duration_ms=r.latency_ms,
        cost_usd=r.cost_usd,
        issues=issues,
        model=r.model,
        provider=r.provider,
    )


def _run_hypotheses(case: EvalCase, state: Any) -> CaseResult:
    from defensefood.agent.briefs.hypotheses import generate_hypotheses

    hs, dest, origin = case.target_key.split("/")
    t0 = time.perf_counter()
    issues: list[str] = []
    try:
        r = generate_hypotheses(
            hs, int(dest), int(origin), state=state, verify="fast"
        )
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            use_case=case.use_case,
            target_key=case.target_key,
            label=case.label,
            passed=False,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            cost_usd=0.0,
            issues=[f"raised: {type(exc).__name__}: {exc}"],
        )
    if len(r.hset.hypotheses) < 2:
        issues.append(f"only {len(r.hset.hypotheses)} hypotheses; need at least 2")
    if r.cost_usd > case.max_cost_usd:
        issues.append(
            f"cost {r.cost_usd:.4f} exceeded cap {case.max_cost_usd:.4f}"
        )
    return CaseResult(
        use_case=case.use_case,
        target_key=case.target_key,
        label=case.label,
        passed=not issues,
        duration_ms=r.latency_ms,
        cost_usd=r.cost_usd,
        issues=issues,
        model=r.model,
        provider=r.provider,
    )


def _run_anomaly(case: EvalCase, state: Any) -> CaseResult:
    from defensefood.agent.briefs.anomaly_explainer import generate_anomaly_explanation

    hs, dest, origin = case.target_key.split("/")
    t0 = time.perf_counter()
    issues: list[str] = []
    try:
        r = generate_anomaly_explanation(
            hs, int(dest), int(origin), state=state, verify="fast"
        )
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            use_case=case.use_case,
            target_key=case.target_key,
            label=case.label,
            passed=False,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            cost_usd=0.0,
            issues=[f"raised: {type(exc).__name__}: {exc}"],
        )
    if r.cost_usd > case.max_cost_usd:
        issues.append(
            f"cost {r.cost_usd:.4f} exceeded cap {case.max_cost_usd:.4f}"
        )
    return CaseResult(
        use_case=case.use_case,
        target_key=case.target_key,
        label=case.label,
        passed=not issues,
        duration_ms=r.latency_ms,
        cost_usd=r.cost_usd,
        issues=issues,
        model=r.model,
        provider=r.provider,
    )


_RUNNERS: dict[str, Callable[[EvalCase, Any], CaseResult]] = {
    "lane_brief": _run_lane_brief,
    "country_brief": _run_country_brief,
    "period_shift": _run_period_shift,
    "hypotheses": _run_hypotheses,
    "explain_anomaly": _run_anomaly,
}


def _run_qa_case(case: QACase, state: Any) -> CaseResult:
    from defensefood.agent.qa.runner import handle_query

    t0 = time.perf_counter()
    issues: list[str] = []
    try:
        r = handle_query(case.question, state=state)
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            use_case="qa",
            target_key=case.question[:80],
            label=case.question[:80],
            passed=False,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            cost_usd=0.0,
            issues=[f"raised: {type(exc).__name__}: {exc}"],
        )
    if r.classification.intent != case.required_intent:
        issues.append(
            f"intent {r.classification.intent} (expected {case.required_intent})"
        )
    if r.classification.in_scope != case.required_in_scope:
        issues.append(
            f"in_scope={r.classification.in_scope} (expected {case.required_in_scope})"
        )
    ans = (r.turn.answer_markdown or "").lower()
    for term in case.required_mentions:
        if term.lower() not in ans:
            issues.append(f"answer missing mention: {term}")
    if r.cost_usd > case.max_cost_usd:
        issues.append(
            f"cost {r.cost_usd:.4f} exceeded cap {case.max_cost_usd:.4f}"
        )
    return CaseResult(
        use_case="qa",
        target_key=case.question[:80],
        label=case.question[:80],
        passed=not issues,
        duration_ms=r.latency_ms,
        cost_usd=r.cost_usd,
        issues=issues,
        model=r.model,
        provider=r.provider,
    )


# ── orchestration ─────────────────────────────────────────────────────────


def _bootstrap_state() -> Any:
    """Build the production AppState (lazy load + corpus indices)."""
    from defensefood.api.dependencies import get_state

    return get_state()


def _write_reports(results: list[CaseResult], *, prefix: str) -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat().replace("-", "")
    json_path = OUTPUT_DIR / f"{prefix}_{today}.json"
    csv_path = OUTPUT_DIR / f"{prefix}_{today}.csv"

    payload = {
        "generated_at_iso": date.today().isoformat(),
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "total_cost_usd": round(sum(r.cost_usd for r in results), 4),
            "mean_duration_ms": int(
                sum(r.duration_ms for r in results) / max(len(results), 1)
            ),
        },
        "results": [
            {
                "use_case": r.use_case,
                "target_key": r.target_key,
                "label": r.label,
                "passed": r.passed,
                "duration_ms": r.duration_ms,
                "cost_usd": round(r.cost_usd, 4),
                "issues": r.issues,
                "model": r.model,
                "provider": r.provider,
            }
            for r in results
        ],
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "use_case",
                "target_key",
                "label",
                "passed",
                "duration_ms",
                "cost_usd",
                "issues",
                "model",
                "provider",
            ]
        )
        for r in results:
            w.writerow(
                [
                    r.use_case,
                    r.target_key,
                    r.label,
                    "PASS" if r.passed else "FAIL",
                    r.duration_ms,
                    f"{r.cost_usd:.4f}",
                    " | ".join(r.issues),
                    r.model,
                    r.provider,
                ]
            )
    return json_path, csv_path


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Agent evaluation harness.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan without firing the LLM. Useful for CI smoke checks.",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Run only cases for a single use_case (e.g. 'lane_brief').",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="agent_eval",
        help="Output filename prefix.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    cases: list[EvalCase] = list(GOLDEN_CASES)
    qa_cases: list[QACase] = list(QA_CASES)
    if args.only:
        cases = [c for c in cases if c.use_case == args.only]
        if args.only != "qa":
            qa_cases = []

    if args.dry_run:
        print(f"Plan: {len(cases)} brief cases + {len(qa_cases)} QA cases")
        for c in cases:
            print(f"  [{c.use_case}] {c.label}  (cap=${c.max_cost_usd:.4f})")
        for q in qa_cases:
            print(f"  [qa] {q.question[:64]}  (intent={q.required_intent})")
        return 0

    logger.info("Building corpus state...")
    state = _bootstrap_state()
    logger.info("State ready; running %d brief cases", len(cases))

    results: list[CaseResult] = []
    for c in cases:
        runner = _RUNNERS.get(c.use_case)
        if runner is None:
            results.append(
                CaseResult(
                    use_case=c.use_case,
                    target_key=c.target_key,
                    label=c.label,
                    passed=False,
                    duration_ms=0,
                    cost_usd=0.0,
                    issues=[f"no runner for use_case {c.use_case!r}"],
                )
            )
            continue
        logger.info("Running %s :: %s", c.use_case, c.label)
        results.append(runner(c, state))

    for q in qa_cases:
        logger.info("QA :: %s", q.question[:64])
        results.append(_run_qa_case(q, state))

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    total_cost = sum(r.cost_usd for r in results)
    logger.info(
        "Done. passed=%d failed=%d total_cost=$%.4f",
        passed,
        failed,
        total_cost,
    )
    json_path, csv_path = _write_reports(results, prefix=args.prefix)
    logger.info("Wrote %s", json_path)
    logger.info("Wrote %s", csv_path)

    return 0 if failed == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
