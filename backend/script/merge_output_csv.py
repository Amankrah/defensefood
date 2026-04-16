"""
Merge all CSV files in backend/script/output/ into a single CSV file for analysis.

Reads every *.csv in the output directory, concatenates them with consistent
columns, optionally deduplicates, and writes one merged file.
"""

import os
from pathlib import Path

import pandas as pd


# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
MERGED_FILENAME = "merged_trade_data.csv"
DROP_DUPLICATES = True  # Set False to keep all rows including exact duplicates


# ─────────────────────────────────────────────
#  MERGE
# ─────────────────────────────────────────────

def get_csv_files(directory: Path) -> list[Path]:
    """Return sorted paths to all .csv files in directory."""
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.csv"), key=lambda p: p.name)


def merge_output_csv(
    output_dir: Path = OUTPUT_DIR,
    merged_filename: str = MERGED_FILENAME,
    drop_duplicates: bool = DROP_DUPLICATES,
    exclude_merged: bool = True,
) -> Path:
    """
    Merge all CSVs in output_dir into one CSV.

    Args:
        output_dir: Directory containing the CSV files.
        merged_filename: Name of the merged output file.
        drop_duplicates: If True, drop exact duplicate rows.
        exclude_merged: If True, do not include the merged file itself if present.

    Returns:
        Path to the written merged CSV.
    """
    csv_files = get_csv_files(output_dir)
    if exclude_merged and merged_filename:
        csv_files = [p for p in csv_files if p.name != merged_filename]
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {output_dir}")

    frames = []
    for path in csv_files:
        try:
            df = pd.read_csv(path)
            if df.empty:
                print(f"  [skip empty] {path.name}")
                continue
            frames.append(df)
        except Exception as e:
            print(f"  [error] {path.name}: {e}")
            continue

    if not frames:
        raise ValueError("No valid (non-empty) CSV data to merge.")

    merged = pd.concat(frames, ignore_index=True)

    if drop_duplicates:
        n_before = len(merged)
        merged = merged.drop_duplicates()
        n_after = len(merged)
        if n_before != n_after:
            print(f"  Dropped {n_before - n_after} duplicate row(s).")

    out_path = output_dir / merged_filename
    merged.to_csv(out_path, index=False)
    print(f"[OK] Merged {len(csv_files)} file(s) → {len(merged)} rows → {out_path}")
    return out_path


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    merge_output_csv(
        output_dir=OUTPUT_DIR,
        merged_filename=MERGED_FILENAME,
        drop_duplicates=DROP_DUPLICATES,
    )
