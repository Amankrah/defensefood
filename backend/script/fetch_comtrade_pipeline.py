"""
UN Comtrade Data Fetching Pipeline

This pipeline fetches bilateral trade data (trade_qty and trade_value)
between countries based on RASFF notification data.

Country pairs are loaded from updated_data_rasff_window.xlsx:
  - From country: origin column
  - To countries: for_followUp column (comma-separated)

HS codes are loaded from unique_commodities_hs_cpc.csv.

Usage:
    # Fetch all trade pairs from RASFF data
    python fetch_comtrade_pipeline.py --from-rasff --years 2022,2023

    # Fetch specific country pair
    python fetch_comtrade_pipeline.py --reporter France --partner Belgium --years 2022

Environment:
    Set COMTRADE_SUBSCRIPTION_KEYS (comma-separated) or COMTRADE_SUBSCRIPTION_KEY
    in backend/script/.env. On HTTP 403 quota, the fetcher rotates to the next key
    automatically; the run stops only when every key is exhausted.
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime
import pandas as pd
import requests


# Comtrade exposes two distinct limits:
#   * HTTP 429 "Rate limit is exceeded. Try again in N seconds." -- a transient
#     burst throttle. We back off (honouring N) and RETRY the same call.
#   * HTTP 403 "Out of call volume quota..." -- the daily/volume cap. We stop the
#     whole run cleanly; --resume continues once it replenishes.
MAX_429_RETRIES = 6
_DEFAULT_BACKOFF_CAP = 30


# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from defensefood.ingestion.comtrade_keys import QuotaExhausted  # noqa: E402

from comtrade_fetcher import (
    fetch_bilateral_trade,
    fetch_trade_data,
    response_to_dataframe,
    extract_trade_values,
    save_to_csv,
    save_to_json,
)
from hs_codes_loader import (
    get_unique_hs_codes,
    get_hs_codes_with_names,
    filter_hs_codes_by_chapter,
    normalize_hs_code,
)
from country_loader import (
    get_m49_code,
    get_trade_pairs_with_hs_codes,
    get_unique_country_pairs,
    extract_trade_pairs,
    M49_COUNTRY_CODES,
    print_country_summary,
)
from checkpoint import CheckpointManager


# ─────────────────────────────────────────────
#  OUTPUT DIRECTORY
# ─────────────────────────────────────────────

def get_output_dir() -> Path:
    """Get or create output directory for downloaded data."""
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


# ─────────────────────────────────────────────
#  PIPELINE FUNCTIONS
# ─────────────────────────────────────────────

def run_bilateral_pipeline(
    reporter: str,
    partner: str,
    years: list[str],
    hs_codes: list[str] = None,
    flow_code: str = "MX",
    batch_size: int = 10,
    delay_seconds: float = 1.0,
    reporter_name: str = None,
    partner_name: str = None,
) -> pd.DataFrame:
    """
    Run the full bilateral trade data pipeline.

    Args:
        reporter: Reporter country M49 code
        partner: Partner country M49 code
        years: List of years to fetch
        hs_codes: List of HS codes (if None, uses all from CSV)
        flow_code: "M" = imports, "X" = exports, "MX" = both
        batch_size: Number of HS codes to process per batch
        delay_seconds: Delay between API calls
        reporter_name: Country name for display
        partner_name: Country name for display

    Returns:
        DataFrame with trade data
    """
    # Resolve country codes if names provided
    reporter_code = get_m49_code(reporter) if not reporter.isdigit() else reporter
    partner_code = get_m49_code(partner) if not partner.isdigit() else partner

    if not reporter_code:
        print(f"[Error] Could not resolve country code for: {reporter}")
        return pd.DataFrame()
    if not partner_code:
        print(f"[Error] Could not resolve country code for: {partner}")
        return pd.DataFrame()

    display_reporter = reporter_name or reporter
    display_partner = partner_name or partner

    print("=" * 60)
    print("UN Comtrade Bilateral Trade Data Pipeline")
    print("=" * 60)
    print(f"Reporter: {display_reporter} (Code: {reporter_code})")
    print(f"Partner:  {display_partner} (Code: {partner_code})")
    print(f"Years:    {years}")
    print(f"Flow:     {flow_code} (M=imports, X=exports, MX=both)")
    print("=" * 60)

    # Load HS codes if not provided
    if hs_codes is None:
        print("\nLoading HS codes from commodities CSV...")
        hs_codes = get_unique_hs_codes()
        print(f"Found {len(hs_codes)} unique HS codes")

    if not hs_codes:
        print("[Warning] No HS codes to process.")
        return pd.DataFrame()

    # Process in batches
    all_results = []
    total_batches = (len(hs_codes) + batch_size - 1) // batch_size

    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(hs_codes))
        batch_codes = hs_codes[start_idx:end_idx]

        print(f"\n--- Batch {batch_num + 1}/{total_batches} ---")
        print(f"Processing HS codes: {batch_codes}")

        batch_df = fetch_bilateral_trade(
            reporter_code=reporter_code,
            partner_code=partner_code,
            hs_codes=batch_codes,
            periods=years,
            flow_code=flow_code,
            delay_seconds=delay_seconds,
        )

        if not batch_df.empty:
            all_results.append(batch_df)

    # Combine all results
    if all_results:
        combined_df = pd.concat(all_results, ignore_index=True)

        # Generate output filename
        output_dir = get_output_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"trade_{display_reporter}_{display_partner}_{'_'.join(years)}_{timestamp}.csv"
        # Clean filename
        filename = filename.replace(" ", "_").replace(",", "_")
        output_path = output_dir / filename

        # Save results
        save_to_csv(combined_df, str(output_path))

        print("\n" + "=" * 60)
        print("PIPELINE COMPLETE")
        print("=" * 60)
        print(f"Total records: {len(combined_df)}")
        print(f"Output file:   {output_path}")

        # Summary statistics
        if "primaryValue" in combined_df.columns:
            total_value = combined_df["primaryValue"].sum()
            print(f"Total trade value: ${total_value:,.2f} USD")

        if "netWgt" in combined_df.columns:
            total_weight = combined_df["netWgt"].sum()
            print(f"Total net weight:  {total_weight:,.2f} kg")

        return combined_df
    else:
        print("\n[Warning] No data fetched.")
        return pd.DataFrame()


def run_rasff_pipeline(
    years: list[str],
    flow_code: str = "MX",
    batch_size: int = 10,
    delay_seconds: float = 1.0,
    limit_pairs: int = None,
    use_pair_hs_codes: bool = True,
    resume: bool = False,
) -> pd.DataFrame:
    """
    Run pipeline for all country pairs from RASFF data.

    Args:
        years: List of years to fetch
        flow_code: Trade flow direction
        batch_size: HS codes per batch
        delay_seconds: API rate limit delay
        limit_pairs: Limit number of country pairs to process (for testing)
        use_pair_hs_codes: If True, use HS codes specific to each country pair
        resume: If True, resume from last checkpoint

    Returns:
        Combined DataFrame with all trade data
    """
    # Initialize checkpoint manager
    checkpoint_mgr = CheckpointManager()

    print("=" * 60)
    print("RASFF-Based Trade Data Pipeline")
    print("=" * 60)
    print(f"Years: {years}")
    print(f"Flow:  {flow_code}")
    print(f"Resume: {resume}")
    print("=" * 60)

    # Load country pairs with their HS codes
    pairs_df = get_trade_pairs_with_hs_codes()

    print(f"\nLoaded {len(pairs_df)} unique country pairs from RASFF data")

    if limit_pairs:
        pairs_df = pairs_df.head(limit_pairs)
        print(f"Limited to {limit_pairs} pairs for this run")

    total_pairs = len(pairs_df)

    # Handle checkpoint/resume
    output_dir = get_output_dir()
    checkpoint = None

    if resume:
        checkpoint = checkpoint_mgr.load_checkpoint()
        if checkpoint:
            checkpoint_mgr.print_status(checkpoint)
            print(f"\nResuming from checkpoint...")
            print(f"Skipping {checkpoint.completed_pairs} already completed pairs")
        else:
            print("[Warning] No checkpoint found. Starting fresh.")
            resume = False

    if not resume:
        # Create new checkpoint
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"rasff_trade_all_pairs_{'_'.join(years)}_{timestamp}.csv"
        checkpoint = checkpoint_mgr.create_checkpoint(
            years=years,
            flow_code=flow_code,
            total_pairs=total_pairs,
            output_file=str(output_dir / output_file),
        )
        print(f"\nNew run started. Checkpoint created.")

    all_results = []
    skipped_count = 0
    processed_count = 0

    for idx, row in pairs_df.iterrows():
        from_code = row["from_code"]
        to_code = row["to_code"]
        from_name = row["from_country"]
        to_name = row["to_country"]
        pair_key = checkpoint_mgr.get_pair_key(from_code, to_code)

        # Skip if already completed
        if checkpoint_mgr.is_pair_completed(checkpoint, from_code, to_code):
            skipped_count += 1
            continue

        # Use pair-specific HS codes or all HS codes
        if use_pair_hs_codes:
            hs_codes = row["hs_codes"]
        else:
            hs_codes = None  # Will load all from CSV

        processed_count += 1
        print(f"\n{'='*60}")
        print(f"Processing pair {checkpoint.completed_pairs + processed_count}/{total_pairs}: {from_name} -> {to_name}")
        if skipped_count > 0:
            print(f"(Skipped {skipped_count} already completed pairs)")
        print(f"HS codes: {len(hs_codes) if hs_codes else 'all'}")
        print("=" * 60)

        df = run_bilateral_pipeline(
            reporter=from_code,
            partner=to_code,
            years=years,
            hs_codes=hs_codes,
            flow_code=flow_code,
            batch_size=batch_size,
            delay_seconds=delay_seconds,
            reporter_name=from_name,
            partner_name=to_name,
        )

        records_added = 0
        if not df.empty:
            # Add source country info
            df["source_from_country"] = from_name
            df["source_to_country"] = to_name
            all_results.append(df)
            records_added = len(df)

            # Append to output file incrementally
            output_path = Path(checkpoint.output_file)
            if output_path.exists():
                df.to_csv(output_path, mode='a', header=False, index=False)
            else:
                df.to_csv(output_path, index=False)

        # Update checkpoint
        checkpoint_mgr.update_checkpoint(
            checkpoint,
            pair_key,
            records_added,
            failed=(records_added == 0),
        )

        print(f"[Checkpoint] Progress: {checkpoint.completed_pairs}/{total_pairs} pairs, {checkpoint.total_records} records")

    # Final summary
    print("\n" + "=" * 60)
    print("FULL RASFF PIPELINE COMPLETE")
    print("=" * 60)
    print(f"Total country pairs:   {total_pairs}")
    print(f"Pairs processed:       {processed_count}")
    print(f"Pairs skipped:         {skipped_count}")
    print(f"Total records:         {checkpoint.total_records}")
    print(f"Output file:           {checkpoint.output_file}")

    # Load and return final data
    output_path = Path(checkpoint.output_file)
    if output_path.exists():
        combined_df = pd.read_csv(output_path)
        if "primaryValue" in combined_df.columns:
            total_value = combined_df["primaryValue"].sum()
            print(f"Total trade value:     ${total_value:,.2f} USD")
        return combined_df
    else:
        print("\n[Warning] No data fetched from any pair.")
        return pd.DataFrame()


# ─────────────────────────────────────────────
#  ALL-PARTNERS PIPELINE (for correct OCS / HHI)
# ─────────────────────────────────────────────

# EU27 reporter M49 codes -- the importing destinations in the RASFF dataset.
# For Section 2 we need each destination's FULL import-partner breakdown so the
# OCS denominator (total imports) and HHI (concentration) are complete, rather
# than limited to the curated RASFF origin pairs.
EU27_REPORTERS = [
    "40", "56", "100", "191", "196", "203", "208", "233", "246", "251",
    "276", "300", "348", "372", "380", "428", "440", "442", "470", "528",
    "616", "620", "642", "703", "705", "724", "752",
]


def get_rasff_hs_codes() -> list[str]:
    """Every HS code that appears in the RASFF notifications (zero-padded).

    Taken straight from the RASFF `hs_code` column so it captures all flagged
    commodities regardless of which destination role surfaced them (not just the
    origin->follow-up pairs). The dependency model only uses these, so scoping the
    all-partners fetch to them instead of all 142 concordance codes cuts call
    volume ~4x.
    """
    from country_loader import load_rasff_data

    df = load_rasff_data()
    codes = set()
    if "hs_code" in df.columns:
        for c in df["hs_code"].dropna().unique():
            norm = normalize_hs_code(c)
            if norm:
                codes.add(norm)
    return sorted(codes)


def _clean_all_partners_response(df: pd.DataFrame) -> pd.DataFrame:
    """Reduce an all-partners Comtrade response to one row per bilateral partner.

    Comtrade returns a 'World' aggregate (partnerCode 0) and may break results
    down by a second partner dimension. We keep only the primary-partner
    aggregate (partner2Code == World/0) and drop the World partner row so that
    summing partners gives the reporter's total without double counting.
    """
    if df.empty:
        return df
    if "partner2Code" in df.columns:
        df = df[df["partner2Code"].astype(str).isin(["0", "0.0", "World"])]
    if "partnerCode" in df.columns:
        df = df[~df["partnerCode"].astype(str).isin(["0", "0.0"])]
    return df


def _retry_after_seconds(err: requests.exceptions.HTTPError, attempt: int) -> int:
    """Seconds to wait before retrying a 429, from Retry-After / body / backoff."""
    resp = getattr(err, "response", None)
    if resp is not None:
        headers = getattr(resp, "headers", None) or {}
        if hasattr(headers, "get"):
            ra = headers.get("Retry-After")
            if ra:
                try:
                    return max(1, int(float(ra)))
                except (ValueError, TypeError):
                    pass
        text = getattr(resp, "text", "") or ""
        m = re.search(r"in\s+(\d+)\s+second", text)
        if m:
            return max(1, int(m.group(1)))
    return min(2 ** attempt, _DEFAULT_BACKOFF_CAP)


def _fetch_one(reporter_code: str, hs: str, flow: str, period: str, max_records: int) -> dict:
    """One all-partners Comtrade call; 429 retries; 403 rotates keys then retries."""
    for attempt in range(MAX_429_RETRIES + 1):
        try:
            return fetch_trade_data(
                type_code="C", freq_code="A", cl_code="HS",
                reporter_code=reporter_code, partner_code=None,  # all partners
                cmd_code=hs, flow_code=flow, period=period, max_records=max_records,
            )
        except QuotaExhausted:
            raise  # all keys exhausted -- resumable stop for the pipeline
        except requests.exceptions.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            if status == 429 and attempt < MAX_429_RETRIES:
                wait = _retry_after_seconds(e, attempt)
                print(f"   [429] burst limit; backing off {wait}s "
                      f"(retry {attempt + 1}/{MAX_429_RETRIES})")
                time.sleep(wait)
                continue
            raise  # 429 exhausted, or any other HTTP error -> caller decides


def fetch_all_partner_trade(
    reporter_code: str,
    hs_code: str,
    periods: list[str],
    flow_codes: tuple[str, ...] = ("M", "X"),
    delay_seconds: float = 1.0,
    max_records: int = 2000,
    combine_flows: bool = False,
) -> tuple[pd.DataFrame, bool]:
    """Fetch a reporter's trade with ALL partners for one HS code.

    `partner_code` is omitted so Comtrade returns every reported partner. Imports
    (M) feed OCS/HHI; exports (X) feed the DS' supply balance (P + M - X).

    Calls are minimised: all years go in one request (period="2022,2023"), and
    with `combine_flows` the M and X flows go in one request too -> a single call
    per (reporter, HS). Returns (dataframe, all_ok); `all_ok` is False if any call
    errored for a non-quota reason, so the job is retried on --resume rather than
    frozen with holes. A genuine empty result still counts as success. HTTP 403
    (quota) raises QuotaExhausted to stop the run; 429 is retried inside _fetch_one.
    """
    hs = normalize_hs_code(hs_code) or str(hs_code)
    period_param = ",".join(str(p) for p in periods)
    flow_calls = [",".join(flow_codes)] if combine_flows else list(flow_codes)

    frames = []
    all_ok = True
    for flow in flow_calls:
        print(f"\n-- Reporter {reporter_code} | HS {hs} | {period_param} | Flow {flow} | ALL partners")
        try:
            raw = _fetch_one(reporter_code, hs, flow, period_param, max_records)
            df = _clean_all_partners_response(response_to_dataframe(raw))
            if not df.empty:
                frames.append(extract_trade_values(df))
        except QuotaExhausted:
            raise  # bubble up to stop the whole run cleanly
        except Exception as e:
            print(f"   [Skipped] {reporter_code} HS{hs} {period_param} {flow}: {e}")
            all_ok = False
        time.sleep(delay_seconds)

    df_out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return df_out, all_ok


def run_all_partners_pipeline(
    years: list[str],
    reporters: list[str] = None,
    hs_codes: list[str] = None,
    flow_code: str = "MX",
    delay_seconds: float = 1.0,
    resume: bool = False,
    limit: int = None,
    combine_flows: bool = False,
) -> pd.DataFrame:
    """Fetch every (reporter, HS) destination's full partner breakdown.

    Output is a single ``comtrade_all_partners_<years>_<ts>.csv`` that the
    dependency loader prefers over the curated RASFF-pair file, giving complete
    OCS / HHI denominators. Uses its own checkpoint so it doesn't collide with
    the bilateral RASFF run.
    """
    reporters = reporters or EU27_REPORTERS
    flow_codes = ("M", "X") if flow_code == "MX" else (flow_code,)

    ckpt_mgr = CheckpointManager(checkpoint_name="all_partners_checkpoint.json")
    output_dir = get_output_dir()

    checkpoint = None
    if resume:
        checkpoint = ckpt_mgr.load_checkpoint()
        if checkpoint:
            # Sticky scope: reuse the HS set the run was started with so you don't
            # have to remember --rasff-hs on every resume.
            if checkpoint.hs_codes:
                hs_codes = checkpoint.hs_codes
        else:
            print("[Warning] No all-partners checkpoint found. Starting fresh.")
            resume = False

    if hs_codes is None:
        hs_codes = get_unique_hs_codes()
        print(f"Loaded {len(hs_codes)} HS codes from commodities CSV")

    jobs = [(r, h) for r in reporters for h in hs_codes]
    if limit:
        jobs = jobs[:limit]
    total = len(jobs)

    print("=" * 60)
    print("ALL-PARTNERS Trade Pipeline (Section 2 OCS/HHI)")
    print("=" * 60)
    print(f"Reporters: {len(reporters)}  HS codes: {len(hs_codes)}  Jobs: {total}")
    print(f"Years: {years}  Flow: {flow_code}  Resume: {resume}")
    print("=" * 60)

    if resume and checkpoint:
        ckpt_mgr.print_status(checkpoint)
        print(f"Resuming; skipping {checkpoint.completed_pairs} completed jobs")
        # Backfill scope + total for checkpoints created before stickiness existed.
        if not checkpoint.hs_codes:
            checkpoint.hs_codes = hs_codes
        checkpoint.total_pairs = total
        ckpt_mgr._save(checkpoint)
    if not resume:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"comtrade_all_partners_{'_'.join(years)}_{timestamp}.csv"
        checkpoint = ckpt_mgr.create_checkpoint(
            years=years,
            flow_code=flow_code,
            total_pairs=total,
            output_file=str(output_dir / output_file),
            hs_codes=hs_codes,
        )

    processed = skipped = 0
    stopped_for_rate_limit = False
    for i, (reporter, hs) in enumerate(jobs, 1):
        key = ckpt_mgr.get_pair_key(reporter, hs)
        if ckpt_mgr.is_pair_completed(checkpoint, reporter, hs):
            skipped += 1
            continue
        processed += 1
        print(f"\n[{i}/{total}] reporter={reporter} HS={hs}")

        try:
            df, all_ok = fetch_all_partner_trade(
                reporter, hs, years, flow_codes, delay_seconds, combine_flows=combine_flows
            )
        except QuotaExhausted as e:
            # Abort cleanly. This job is NOT checkpointed, so --resume retries it
            # in full; everything before it is already saved.
            print("\n" + "!" * 60)
            print(f"[QUOTA] {e}")
            print("Out of call-volume quota. Progress saved. Resume once it replenishes:")
            print("    python fetch_comtrade_pipeline.py --all-partners --resume")
            print("!" * 60)
            stopped_for_rate_limit = True
            break

        records = 0
        if not df.empty:
            out_path = Path(checkpoint.output_file)
            if out_path.exists():
                df.to_csv(out_path, mode="a", header=False, index=False)
            else:
                df.to_csv(out_path, index=False)
            records = len(df)

        # Mark complete only when every year/flow call succeeded (empty is OK).
        # A partially-errored job stays uncompleted so --resume retries it.
        ckpt_mgr.update_checkpoint(checkpoint, key, records, failed=not all_ok)

    print("\n" + "=" * 60)
    print("ALL-PARTNERS PIPELINE " + ("STOPPED (quota)" if stopped_for_rate_limit else "COMPLETE"))
    print(f"Jobs processed: {processed}  skipped: {skipped}  records: {checkpoint.total_records}")
    print(f"Completed jobs: {checkpoint.completed_pairs}/{total}  failed(retryable): {len(checkpoint.failed_pairs)}")
    print(f"Output: {checkpoint.output_file}")
    if stopped_for_rate_limit:
        print("Re-run with --resume to continue.")
    print("=" * 60)

    out_path = Path(checkpoint.output_file)
    return pd.read_csv(out_path) if out_path.exists() else pd.DataFrame()


def run_single_query(
    reporter: str,
    partner: str,
    hs_code: str,
    year: str,
    flow_code: str = "X",
):
    """
    Run a single query for debugging/testing.
    """
    reporter_code = get_m49_code(reporter) if not reporter.isdigit() else reporter
    partner_code = get_m49_code(partner) if not partner.isdigit() else partner

    print(f"Fetching: {reporter} -> {partner}, HS: {hs_code}, Year: {year}, Flow: {flow_code}")

    # Handle "MX" by making separate calls for imports and exports
    flow_codes = ["M", "X"] if flow_code == "MX" else [flow_code]
    all_dfs = []

    for fc in flow_codes:
        print(f"  -> Flow: {fc}")
        try:
            response = fetch_trade_data(
                type_code="C",
                freq_code="A",
                cl_code="HS",
                reporter_code=reporter_code,
                partner_code=partner_code,
                cmd_code=hs_code,
                flow_code=fc,
                period=year,
            )

            df = response_to_dataframe(response)
            if not df.empty:
                df = extract_trade_values(df)
                all_dfs.append(df)
        except Exception as e:
            print(f"     [Error] {e}")

    if all_dfs:
        combined = pd.concat(all_dfs, ignore_index=True)
        print("\nResults:")
        print(combined.to_string())
        return combined
    else:
        print("No data returned.")
        return None


# ─────────────────────────────────────────────
#  SPECIALIZED PIPELINES BY COMMODITY TYPE
# ─────────────────────────────────────────────

def fetch_seafood_trade(reporter: str, partner: str, years: list[str]):
    """Fetch trade data for seafood commodities (Chapter 03)."""
    hs_codes = filter_hs_codes_by_chapter("03")
    print(f"Found {len(hs_codes)} seafood HS codes")
    return run_bilateral_pipeline(reporter, partner, years, hs_codes=hs_codes)


def fetch_cereals_trade(reporter: str, partner: str, years: list[str]):
    """Fetch trade data for cereals (Chapter 10)."""
    hs_codes = filter_hs_codes_by_chapter("10")
    print(f"Found {len(hs_codes)} cereal HS codes")
    return run_bilateral_pipeline(reporter, partner, years, hs_codes=hs_codes)


def fetch_feed_trade(reporter: str, partner: str, years: list[str]):
    """Fetch trade data for animal feed (Chapter 23)."""
    hs_codes = filter_hs_codes_by_chapter("23")
    print(f"Found {len(hs_codes)} feed HS codes")
    return run_bilateral_pipeline(reporter, partner, years, hs_codes=hs_codes)


# ─────────────────────────────────────────────
#  CLI INTERFACE
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fetch UN Comtrade bilateral trade data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch FULL partner breakdown for ONLY the RASFF HS codes (recommended: ~4x fewer calls)
  python fetch_comtrade_pipeline.py --all-partners --rasff-hs --years 2022,2023
  # ...add --combine-flows for another ~2x (one call per reporter/HS) if your tier allows
  python fetch_comtrade_pipeline.py --all-partners --rasff-hs --combine-flows --years 2022,2023
  # ...resume after a quota stop (continues exactly where it left off)
  python fetch_comtrade_pipeline.py --all-partners --resume
  # ...smoke test (first 5 reporter/HS jobs)
  python fetch_comtrade_pipeline.py --all-partners --rasff-hs --years 2022 --limit-pairs 5

  # Fetch ALL country pairs from RASFF data (with their specific HS codes)
  python fetch_comtrade_pipeline.py --from-rasff --years 2022,2023

  # RESUME an interrupted run (continues from last checkpoint)
  python fetch_comtrade_pipeline.py --from-rasff --years 2022,2023 --resume

  # Clear checkpoint and start fresh
  python fetch_comtrade_pipeline.py --clear-checkpoint

  # Fetch RASFF pairs but use ALL HS codes (not pair-specific)
  python fetch_comtrade_pipeline.py --from-rasff --years 2022 --all-hs-codes

  # Test with limited pairs
  python fetch_comtrade_pipeline.py --from-rasff --years 2022 --limit-pairs 5

  # Fetch specific country pair
  python fetch_comtrade_pipeline.py --reporter France --partner Belgium --years 2022,2023

  # Fetch specific HS codes
  python fetch_comtrade_pipeline.py --reporter France --partner Belgium --years 2022 --hs-codes 100630,030617

  # Single query test
  python fetch_comtrade_pipeline.py --reporter France --partner Belgium --years 2022 --hs-codes 100630 --single

  # Show country summary from RASFF
  python fetch_comtrade_pipeline.py --show-countries
"""
    )

    # All-partners mode (Section 2 OCS/HHI)
    parser.add_argument("--all-partners", action="store_true",
                        help="Fetch each reporter's FULL partner breakdown per HS code "
                             "(complete OCS/HHI denominators). Defaults to EU27 reporters.")
    parser.add_argument("--reporters",
                        help="Comma-separated reporter M49 codes for --all-partners "
                             "(default: EU27)")
    parser.add_argument("--rasff-hs", action="store_true",
                        help="Scope --all-partners to only the HS codes present in RASFF "
                             "corridors (~34 instead of 142) -- ~4x fewer calls")
    parser.add_argument("--combine-flows", action="store_true",
                        help="Fetch imports+exports in one call per (reporter, HS) "
                             "(flowCode=M,X) -- halves calls again. Try if your tier supports it.")

    # RASFF mode
    parser.add_argument("--from-rasff", action="store_true",
                        help="Load country pairs from RASFF Excel file")
    parser.add_argument("--limit-pairs", type=int,
                        help="Limit number of country pairs (for testing)")
    parser.add_argument("--all-hs-codes", action="store_true",
                        help="Use all HS codes instead of pair-specific ones")
    parser.add_argument("--show-countries", action="store_true",
                        help="Show country summary from RASFF data and exit")

    # Checkpoint/Resume
    parser.add_argument("--resume", action="store_true",
                        help="Resume from last checkpoint (skips completed pairs)")
    parser.add_argument("--clear-checkpoint", action="store_true",
                        help="Clear existing checkpoint and exit")
    parser.add_argument("--show-checkpoint", action="store_true",
                        help="Show current checkpoint status and exit")

    # Manual mode
    parser.add_argument("--reporter",
                        help="Reporting country name or M49 code")
    parser.add_argument("--partner",
                        help="Partner country name or M49 code")
    parser.add_argument("--years",
                        help="Comma-separated years (e.g., 2021,2022,2023)")
    parser.add_argument("--hs-codes",
                        help="Comma-separated HS codes (optional)")

    # Common options
    parser.add_argument("--flow", default="MX",
                        help="Flow code: M=imports, X=exports, MX=both (default: MX)")
    parser.add_argument("--batch-size", type=int, default=10,
                        help="HS codes per batch (default: 10)")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Delay between API calls in seconds (default: 1.0)")
    parser.add_argument("--single", action="store_true",
                        help="Run single query mode for testing")
    parser.add_argument("--category",
                        choices=["seafood", "cereals", "feed"],
                        help="Fetch by commodity category")

    args = parser.parse_args()

    # Initialize checkpoint manager for checkpoint commands
    checkpoint_mgr = CheckpointManager()

    # Clear checkpoint
    if args.clear_checkpoint:
        checkpoint_mgr.clear_checkpoint()
        return

    # Show checkpoint status
    if args.show_checkpoint:
        checkpoint = checkpoint_mgr.load_checkpoint()
        if checkpoint:
            checkpoint_mgr.print_status(checkpoint)
        else:
            print("[Info] No checkpoint found.")
        return

    # Show countries summary
    if args.show_countries:
        print_country_summary()
        return

    # Validate required args
    if not args.from_rasff and not args.all_partners and not (args.reporter and args.partner):
        parser.error("One of --all-partners, --from-rasff, or both --reporter and --partner is required")

    if not args.years and not args.show_countries and not args.resume:
        parser.error("--years is required (or use --resume to continue previous run)")

    # Handle resume - load years from the matching checkpoint if not provided
    if args.resume and not args.years:
        resume_name = "all_partners_checkpoint.json" if args.all_partners else "pipeline_checkpoint.json"
        checkpoint = CheckpointManager(checkpoint_name=resume_name).load_checkpoint()
        if checkpoint:
            years = checkpoint.years
            print(f"[Resume] Using years from checkpoint: {years}")
        else:
            parser.error("--years is required (no checkpoint found to resume from)")
    else:
        years = args.years.split(",") if args.years else []

    hs_codes = args.hs_codes.split(",") if args.hs_codes else None

    # All-partners mode - full partner breakdown per (reporter, HS)
    if args.all_partners:
        reporters = args.reporters.split(",") if args.reporters else None
        hs = hs_codes
        if hs is None and args.rasff_hs:
            hs = get_rasff_hs_codes()
            print(f"Scoped to {len(hs)} RASFF HS codes")
        return run_all_partners_pipeline(
            years=years,
            reporters=reporters,
            hs_codes=hs,
            flow_code=args.flow,
            delay_seconds=args.delay,
            resume=args.resume,
            limit=args.limit_pairs,
            combine_flows=args.combine_flows,
        )

    # RASFF mode - load all country pairs from Excel
    if args.from_rasff:
        return run_rasff_pipeline(
            years=years,
            flow_code=args.flow,
            batch_size=args.batch_size,
            delay_seconds=args.delay,
            limit_pairs=args.limit_pairs,
            use_pair_hs_codes=not args.all_hs_codes,
            resume=args.resume,
        )

    # Run by category if specified
    if args.category == "seafood":
        return fetch_seafood_trade(args.reporter, args.partner, years)
    elif args.category == "cereals":
        return fetch_cereals_trade(args.reporter, args.partner, years)
    elif args.category == "feed":
        return fetch_feed_trade(args.reporter, args.partner, years)

    # Single query mode
    if args.single and hs_codes:
        return run_single_query(
            args.reporter,
            args.partner,
            hs_codes[0],
            years[0],
            args.flow,
        )

    # Full pipeline for specific country pair
    return run_bilateral_pipeline(
        reporter=args.reporter,
        partner=args.partner,
        years=years,
        hs_codes=hs_codes,
        flow_code=args.flow,
        batch_size=args.batch_size,
        delay_seconds=args.delay,
    )


if __name__ == "__main__":
    main()
