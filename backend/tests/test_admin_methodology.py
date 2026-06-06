"""Phase 6 — admin cache helpers + CLI tool.

Admin access is CLI-only now (no HTTP endpoints); this file exercises the
SQLite-backed helpers in ``defensefood.agent.cache`` and the ``agent_admin``
script that drives them.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    db_path = tempfile.mktemp(suffix=".db")
    monkeypatch.setenv("DEFENSEFOOD_AGENT_DB_PATH", db_path)
    from defensefood.agent.config import reset_config_cache
    reset_config_cache()
    from defensefood.agent.cache import _INITIALIZED_DBS  # type: ignore[attr-defined]
    _INITIALIZED_DBS.clear()
    yield db_path
    try:
        os.unlink(db_path)
    except OSError:
        pass


from defensefood.agent import cache as agent_cache


def _seed_some_briefs():
    """Drop a handful of brief rows + cost ledger entries into the temp db."""
    agent_cache.store_brief(
        use_case="lane_brief",
        target_key="30771/250/724",
        snapshot_hash="abc",
        brief={
            "headline": "Spain mussels into France",
            "verifier_notes": [
                "style: forbidden phrase used: 'consistent with'",
            ],
        },
        model="claude-sonnet-4-6",
        provider="anthropic",
        cost_usd=0.012,
        latency_ms=15000,
    )
    agent_cache.store_brief(
        use_case="hypotheses",
        target_key="1006/528/586",
        snapshot_hash="abc",
        brief={
            "hset": {
                "hypotheses": [{"headline": "H1"}, {"headline": "H2"}],
                "verifier_notes": [],
            }
        },
        model="claude-opus-4-7",
        provider="anthropic",
        cost_usd=0.15,
        latency_ms=120000,
    )
    agent_cache.record_cost(
        use_case="lane_brief",
        provider="anthropic",
        model="claude-sonnet-4-6",
        tokens_in=1500,
        tokens_out=400,
        usd=0.012,
    )
    agent_cache.record_cost(
        use_case="hypotheses",
        provider="anthropic",
        model="claude-opus-4-7",
        tokens_in=2200,
        tokens_out=600,
        usd=0.15,
    )


# ── cache helpers ─────────────────────────────────────────────────────────


def test_brief_inventory_aggregates_by_use_case():
    _seed_some_briefs()
    inv = agent_cache.brief_inventory()
    by_uc = {row["use_case"]: row for row in inv}
    assert by_uc["lane_brief"]["n"] == 1
    assert by_uc["lane_brief"]["total_cost_usd"] == pytest.approx(0.012)
    assert by_uc["hypotheses"]["n"] == 1
    assert by_uc["hypotheses"]["total_cost_usd"] == pytest.approx(0.15)
    # Ordered by count desc; both rows present.
    assert {r["use_case"] for r in inv} == {"lane_brief", "hypotheses"}


def test_cost_ledger_window_returns_recent_rows():
    _seed_some_briefs()
    rows = agent_cache.cost_ledger_window(days=7)
    assert len(rows) == 2
    use_cases = {r["use_case"] for r in rows}
    assert use_cases == {"lane_brief", "hypotheses"}


def test_list_briefs_filters_and_orders_by_recency():
    _seed_some_briefs()
    all_rows = agent_cache.list_briefs(limit=10)
    assert len(all_rows) == 2
    filt = agent_cache.list_briefs(use_case="hypotheses", limit=10)
    assert len(filt) == 1
    assert filt[0]["model"] == "claude-opus-4-7"


def test_get_brief_full_returns_parsed_brief_or_none():
    _seed_some_briefs()
    row = agent_cache.get_brief_full(1)
    assert row is not None
    assert row["use_case"] == "lane_brief"
    assert isinstance(row["brief"], dict)
    assert row["brief"]["headline"].startswith("Spain mussels")

    assert agent_cache.get_brief_full(999) is None


def test_invalidate_brief_cache_requires_filter():
    _seed_some_briefs()
    with pytest.raises(ValueError, match="provide use_case"):
        agent_cache.invalidate_brief_cache()


def test_invalidate_brief_cache_targeted_delete():
    _seed_some_briefs()
    n = agent_cache.invalidate_brief_cache(use_case="hypotheses")
    assert n == 1
    inv = agent_cache.brief_inventory()
    use_cases = {row["use_case"] for row in inv}
    assert use_cases == {"lane_brief"}


def test_recent_verifier_notes_walks_nested_shapes():
    _seed_some_briefs()
    agent_cache.append_audit(
        use_case="lane_brief",
        target_key="30771/250/724",
        role="assistant",
        content={
            "brief": {
                "headline": "x",
                "verifier_notes": [
                    "style: em-dash replaced",
                    "caveat injected: sci_his",
                ],
            },
            "tool_trace": [],
        },
        brief_id=1,
    )
    rows = agent_cache.recent_verifier_notes(limit=10)
    assert len(rows) >= 1
    notes = next(
        r for r in rows if r["use_case"] == "lane_brief"
    )["notes"]
    assert any("em-dash" in n or "caveat" in n for n in notes)


# ── CLI ───────────────────────────────────────────────────────────────────


def _run_cli(argv: list[str]) -> tuple[int, str]:
    """Invoke the CLI in-process and capture stdout."""
    import io
    import contextlib
    from script.agent_admin import main as cli_main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli_main(argv)
    return rc, buf.getvalue()


def test_cli_stats_human_output():
    _seed_some_briefs()
    rc, out = _run_cli(["stats", "--days", "7"])
    assert rc == 0
    # Pretty-print header bits.
    assert "Totals" in out
    assert "lane_brief" in out
    assert "hypotheses" in out
    assert "$" in out  # USD formatting


def test_cli_stats_json_round_trips():
    _seed_some_briefs()
    rc, out = _run_cli(["stats", "--json", "--days", "7"])
    assert rc == 0
    payload = json.loads(out)
    assert payload["totals"]["briefs"] == 2
    assert payload["totals"]["use_cases"] == 2
    assert {r["use_case"] for r in payload["brief_inventory"]} == {
        "lane_brief",
        "hypotheses",
    }
    assert len(payload["cost_ledger"]) == 2


def test_cli_briefs_filter():
    _seed_some_briefs()
    rc, out = _run_cli(["briefs", "--use-case", "hypotheses"])
    assert rc == 0
    assert "hypotheses" in out
    # lane_brief filtered out.
    assert "lane_brief" not in out


def test_cli_audit_missing_brief_returns_nonzero():
    rc, _ = _run_cli(["audit", "99999"])
    assert rc != 0


def test_cli_audit_prints_payload_and_audit_rows():
    _seed_some_briefs()
    agent_cache.append_audit(
        use_case="lane_brief",
        target_key="30771/250/724",
        role="assistant",
        content={"brief": {"headline": "Spain mussels into France"}},
        tokens_in=1500,
        tokens_out=400,
        brief_id=1,
    )
    rc, out = _run_cli(["audit", "1"])
    assert rc == 0
    assert "Brief #1" in out
    assert "lane_brief" in out
    assert "audit log" in out.lower() or "row" in out.lower()


def test_cli_invalidate_refuses_without_filter():
    rc, _ = _run_cli(["invalidate", "--yes"])
    assert rc == 2


def test_cli_invalidate_deletes_with_yes_flag():
    _seed_some_briefs()
    rc, out = _run_cli(["invalidate", "--use-case", "hypotheses", "--yes"])
    assert rc == 0
    assert "deleted" in out.lower()
    inv = agent_cache.brief_inventory()
    use_cases = {row["use_case"] for row in inv}
    assert use_cases == {"lane_brief"}


def test_cli_methodology_lists_tools_and_prompts():
    rc, out = _run_cli(["methodology"])
    assert rc == 0
    # Tools registered across the build are surfaced.
    assert "submit_lane_brief" in out
    assert "submit_hypotheses" in out
    # Prompt files are listed.
    assert "hypotheses.md" in out
    assert "anomaly_explainer.md" in out


def test_cli_methodology_json_emits_full_prompt_content():
    rc, out = _run_cli(["methodology", "--json", "--prompts"])
    assert rc == 0
    payload = json.loads(out)
    prompt_names = {p["name"] for p in payload["prompts"]}
    assert "hypotheses" in prompt_names
    # The actual markdown content is present (one of the rules we wrote).
    hyp = next(p for p in payload["prompts"] if p["name"] == "hypotheses")
    assert "## Voice" in hyp["content"]


# ── HTTP surface confirms admin endpoints are gone ────────────────────────


def test_admin_http_endpoints_no_longer_exist():
    """Regression: every /admin/* path should now return 404. The endpoints
    were removed in favour of the CLI; this test guarantees they don't
    accidentally come back."""
    from fastapi.testclient import TestClient
    from defensefood.api.main import app

    client = TestClient(app)
    for path in [
        "/api/v1/agent/admin/stats",
        "/api/v1/agent/admin/briefs",
        "/api/v1/agent/admin/briefs/1/audit",
        "/api/v1/agent/admin/verifier-notes",
        "/api/v1/agent/methodology",
    ]:
        r = client.get(path)
        assert r.status_code == 404, f"{path} returned {r.status_code}, expected 404"
    r = client.post("/api/v1/agent/admin/invalidate", json={"use_case": "x"})
    assert r.status_code == 404
