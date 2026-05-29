"""All-partners Comtrade pull: response cleaning, pipeline run (mocked), loader preference.

The network call is mocked, so these run offline. They verify the wiring that
makes OCS/HHI denominators complete:
  * the World aggregate (partnerCode 0) and secondary-partner rows are stripped,
  * the pipeline writes one row per bilateral partner,
  * the dependency loader prefers the all-partners file over the curated pairs.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import requests

# The fetch pipeline lives in backend/script and imports sibling modules.
SCRIPT_DIR = Path(__file__).resolve().parent.parent / "script"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import fetch_comtrade_pipeline as fcp  # noqa: E402
from checkpoint import CheckpointManager  # noqa: E402


def test_clean_all_partners_strips_world_and_secondary():
    raw = pd.DataFrame({
        "period": [2022, 2022, 2022, 2022],
        "reporterCode": [56, 56, 56, 56],
        "partnerCode": [0, 251, 276, 251],     # 0 = World aggregate (drop)
        "partner2Code": [0, 0, 0, 124],         # last row is a 2nd-partner split (drop)
        "cmdCode": ["120740"] * 4,
        "flowCode": ["M"] * 4,
        "netWgt": [12000.0, 8000.0, 2000.0, 500.0],
    })
    cleaned = fcp._clean_all_partners_response(raw)
    partners = set(cleaned["partnerCode"].tolist())
    assert partners == {251, 276}        # World dropped, 2nd-partner split dropped
    assert 0 not in partners


def _fake_response(reporter_code, cmd_code, flow_code, period, **kwargs):
    # Two bilateral partners + a World aggregate that must be filtered out.
    return {
        "data": [
            {"period": period, "reporterCode": int(reporter_code), "partnerCode": 0,
             "partner2Code": 0, "cmdCode": cmd_code, "flowCode": flow_code, "netWgt": 10000.0},
            {"period": period, "reporterCode": int(reporter_code), "partnerCode": 251,
             "partner2Code": 0, "cmdCode": cmd_code, "flowCode": flow_code, "netWgt": 7000.0},
            {"period": period, "reporterCode": int(reporter_code), "partnerCode": 276,
             "partner2Code": 0, "cmdCode": cmd_code, "flowCode": flow_code, "netWgt": 3000.0},
        ]
    }


def test_run_all_partners_pipeline_writes_bilateral_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(fcp, "fetch_trade_data", _fake_response)
    monkeypatch.setattr(fcp, "get_output_dir", lambda: tmp_path)
    # Route the checkpoint into tmp too.
    monkeypatch.setattr(
        fcp, "CheckpointManager",
        lambda **kw: CheckpointManager(checkpoint_dir=tmp_path, **kw),
    )

    df = fcp.run_all_partners_pipeline(
        years=["2022"], reporters=["56"], hs_codes=["120740"],
        flow_code="M", delay_seconds=0.0,
    )
    # World row stripped -> only 2 bilateral partners remain.
    assert len(df) == 2
    assert set(df["partnerCode"]) == {251, 276}
    assert (tmp_path / "all_partners_checkpoint.json").exists()

    # All calls succeeded -> job marked completed (won't be re-fetched on resume).
    cp = CheckpointManager(
        checkpoint_dir=tmp_path, checkpoint_name="all_partners_checkpoint.json"
    ).load_checkpoint()
    assert "56:120740" in cp.completed_pair_keys


def _http_error(status: int, body: str = "") -> requests.exceptions.HTTPError:
    err = requests.exceptions.HTTPError(f"{status}")
    err.response = SimpleNamespace(status_code=status, text=body, headers={})
    return err


def test_quota_403_aborts_and_preserves_progress(tmp_path, monkeypatch):
    def fake(reporter_code, cmd_code, flow_code, period, **kw):
        if str(reporter_code) == "40":  # second job hits the daily quota
            raise _http_error(403, '{"statusCode":403,"message":"Out of call volume quota."}')
        return {"data": [{"period": period, "reporterCode": int(reporter_code),
                          "partnerCode": 251, "partner2Code": 0, "cmdCode": cmd_code,
                          "flowCode": flow_code, "netWgt": 7000.0}]}

    monkeypatch.setattr(fcp, "fetch_trade_data", fake)
    monkeypatch.setattr(fcp, "get_output_dir", lambda: tmp_path)
    monkeypatch.setattr(
        fcp, "CheckpointManager",
        lambda **kw: CheckpointManager(checkpoint_dir=tmp_path, **kw),
    )

    # Reporter 56 succeeds, then 40 triggers the quota abort.
    fcp.run_all_partners_pipeline(
        years=["2022"], reporters=["56", "40"], hs_codes=["120740"],
        flow_code="M", delay_seconds=0.0,
    )

    cp = CheckpointManager(
        checkpoint_dir=tmp_path, checkpoint_name="all_partners_checkpoint.json"
    ).load_checkpoint()
    assert "56:120740" in cp.completed_pair_keys       # prior job saved
    assert "40:120740" not in cp.completed_pair_keys    # aborted job left for --resume
    assert "40:120740" not in cp.failed_pairs           # not frozen as failed either


def test_429_is_retried_then_succeeds(tmp_path, monkeypatch):
    # First call 429s ("try again in 3 seconds"), second call returns data.
    calls = {"n": 0}

    def fake(reporter_code, cmd_code, flow_code, period, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(429, '{"statusCode":429,"message":"Rate limit is exceeded. Try again in 3 seconds."}')
        return {"data": [{"period": period, "reporterCode": int(reporter_code),
                          "partnerCode": 251, "partner2Code": 0, "cmdCode": cmd_code,
                          "flowCode": flow_code, "netWgt": 7000.0}]}

    monkeypatch.setattr(fcp, "fetch_trade_data", fake)
    monkeypatch.setattr(fcp, "get_output_dir", lambda: tmp_path)
    monkeypatch.setattr(fcp.time, "sleep", lambda *_: None)  # don't actually wait
    monkeypatch.setattr(
        fcp, "CheckpointManager",
        lambda **kw: CheckpointManager(checkpoint_dir=tmp_path, **kw),
    )

    df = fcp.run_all_partners_pipeline(
        years=["2022"], reporters=["56"], hs_codes=["120740"],
        flow_code="M", delay_seconds=0.0,
    )
    assert calls["n"] == 2                      # retried once, then succeeded
    assert len(df) == 1                          # data was fetched after backoff
    cp = CheckpointManager(
        checkpoint_dir=tmp_path, checkpoint_name="all_partners_checkpoint.json"
    ).load_checkpoint()
    assert "56:120740" in cp.completed_pair_keys


def test_retry_after_seconds_parses_body():
    err = _http_error(429, "Rate limit is exceeded. Try again in 8 seconds.")
    assert fcp._retry_after_seconds(err, attempt=0) == 8


def test_hs_scope_is_sticky_across_resume(tmp_path, monkeypatch):
    seen_codes = []

    def fake(reporter_code, cmd_code, flow_code, period, **kw):
        seen_codes.append(cmd_code)
        return {"data": [{"period": period, "reporterCode": int(reporter_code),
                          "partnerCode": 251, "partner2Code": 0, "cmdCode": cmd_code,
                          "flowCode": flow_code, "netWgt": 1.0}]}

    monkeypatch.setattr(fcp, "fetch_trade_data", fake)
    monkeypatch.setattr(fcp, "get_output_dir", lambda: tmp_path)
    monkeypatch.setattr(
        fcp, "CheckpointManager",
        lambda **kw: CheckpointManager(checkpoint_dir=tmp_path, **kw),
    )
    # If sticky scope failed, this would fall back to all concordance codes.
    monkeypatch.setattr(fcp, "get_unique_hs_codes", lambda: ["999999"])

    # Fresh run scoped to one HS code.
    fcp.run_all_partners_pipeline(
        years=["2022"], reporters=["56"], hs_codes=["120740"],
        flow_code="M", delay_seconds=0.0,
    )
    cp = CheckpointManager(
        checkpoint_dir=tmp_path, checkpoint_name="all_partners_checkpoint.json"
    ).load_checkpoint()
    assert cp.hs_codes == ["120740"]   # scope persisted

    # Resume WITHOUT passing hs_codes -> must reuse the stored scope, not the
    # 999999 fallback.
    seen_codes.clear()
    fcp.run_all_partners_pipeline(
        years=["2022"], reporters=["56", "276"], hs_codes=None,
        flow_code="M", delay_seconds=0.0, resume=True,
    )
    assert "999999" not in seen_codes
    assert all(c == "120740" for c in seen_codes)


def test_non_rate_limit_error_marks_retryable(tmp_path, monkeypatch):
    def fake(*a, **kw):
        raise ValueError("transient parse glitch")

    monkeypatch.setattr(fcp, "fetch_trade_data", fake)
    monkeypatch.setattr(fcp, "get_output_dir", lambda: tmp_path)
    monkeypatch.setattr(
        fcp, "CheckpointManager",
        lambda **kw: CheckpointManager(checkpoint_dir=tmp_path, **kw),
    )

    fcp.run_all_partners_pipeline(
        years=["2022"], reporters=["56"], hs_codes=["120740"],
        flow_code="M", delay_seconds=0.0,
    )

    cp = CheckpointManager(
        checkpoint_dir=tmp_path, checkpoint_name="all_partners_checkpoint.json"
    ).load_checkpoint()
    assert "56:120740" not in cp.completed_pair_keys   # not marked done
    assert "56:120740" in cp.failed_pairs              # retried on --resume


def test_loader_prefers_all_partners_over_pairs(tmp_path, monkeypatch):
    from defensefood.ingestion import comtrade

    # Older curated pairs file, newer all-partners file.
    pairs = tmp_path / "rasff_trade_all_pairs_2022_2023_x.csv"
    pairs.write_text("cmdCode,reporterCode,partnerCode,period,flowCode,netWgt\n1006,56,251,2022,M,1\n")
    allp = tmp_path / "comtrade_all_partners_2022_2023_y.csv"
    allp.write_text("cmdCode,reporterCode,partnerCode,period,flowCode,netWgt\n1006,56,251,2022,M,2\n")

    monkeypatch.setattr(comtrade, "_output_dir", lambda: tmp_path)
    df = comtrade.load_merged_trade_data()
    # all-partners file wins -> netWgt 2, not 1
    assert df["netWgt"].iloc[0] == 2
