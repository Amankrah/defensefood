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
    Set COMTRADE_SUBSCRIPTION_KEY in your .env file or environment variables.
"""

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

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
    if not args.from_rasff and not (args.reporter and args.partner):
        parser.error("Either --from-rasff or both --reporter and --partner are required")

    if not args.years and not args.show_countries and not args.resume:
        parser.error("--years is required (or use --resume to continue previous run)")

    # Handle resume - load years from checkpoint if not provided
    if args.resume and not args.years:
        checkpoint = checkpoint_mgr.load_checkpoint()
        if checkpoint:
            years = checkpoint.years
            print(f"[Resume] Using years from checkpoint: {years}")
        else:
            parser.error("--years is required (no checkpoint found to resume from)")
    else:
        years = args.years.split(",") if args.years else []

    hs_codes = args.hs_codes.split(",") if args.hs_codes else None

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
