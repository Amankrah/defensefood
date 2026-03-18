"""
Checkpoint Manager for Pipeline Progress Tracking

Saves and loads progress to allow resuming interrupted runs.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Set, Optional
from dataclasses import dataclass, asdict


@dataclass
class CheckpointData:
    """Checkpoint data structure."""
    run_id: str
    started_at: str
    last_updated: str
    years: list
    flow_code: str
    total_pairs: int
    completed_pairs: int
    completed_pair_keys: list  # List of "from_code:to_code" strings
    failed_pairs: list  # Pairs that failed (for retry)
    total_records: int
    output_file: str


class CheckpointManager:
    """Manages checkpoint save/load for pipeline progress."""

    def __init__(self, checkpoint_dir: Path = None):
        if checkpoint_dir is None:
            checkpoint_dir = Path(__file__).parent / "output"
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(exist_ok=True)
        self.checkpoint_file = self.checkpoint_dir / "pipeline_checkpoint.json"

    def create_checkpoint(
        self,
        years: list,
        flow_code: str,
        total_pairs: int,
        output_file: str,
    ) -> CheckpointData:
        """Create a new checkpoint for a fresh run."""
        now = datetime.now().isoformat()
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        checkpoint = CheckpointData(
            run_id=run_id,
            started_at=now,
            last_updated=now,
            years=years,
            flow_code=flow_code,
            total_pairs=total_pairs,
            completed_pairs=0,
            completed_pair_keys=[],
            failed_pairs=[],
            total_records=0,
            output_file=output_file,
        )

        self._save(checkpoint)
        return checkpoint

    def load_checkpoint(self) -> Optional[CheckpointData]:
        """Load existing checkpoint if available."""
        if not self.checkpoint_file.exists():
            return None

        try:
            with open(self.checkpoint_file, "r") as f:
                data = json.load(f)
            return CheckpointData(**data)
        except Exception as e:
            print(f"[Warning] Could not load checkpoint: {e}")
            return None

    def update_checkpoint(
        self,
        checkpoint: CheckpointData,
        pair_key: str,
        records_added: int,
        failed: bool = False,
    ) -> None:
        """Update checkpoint after processing a pair."""
        checkpoint.last_updated = datetime.now().isoformat()

        if failed:
            if pair_key not in checkpoint.failed_pairs:
                checkpoint.failed_pairs.append(pair_key)
        else:
            if pair_key not in checkpoint.completed_pair_keys:
                checkpoint.completed_pair_keys.append(pair_key)
                checkpoint.completed_pairs = len(checkpoint.completed_pair_keys)
            checkpoint.total_records += records_added

        self._save(checkpoint)

    def is_pair_completed(self, checkpoint: CheckpointData, from_code: str, to_code: str) -> bool:
        """Check if a pair has already been processed."""
        pair_key = f"{from_code}:{to_code}"
        return pair_key in checkpoint.completed_pair_keys

    def get_pair_key(self, from_code: str, to_code: str) -> str:
        """Generate a unique key for a country pair."""
        return f"{from_code}:{to_code}"

    def clear_checkpoint(self) -> None:
        """Delete the checkpoint file to start fresh."""
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
            print("[OK] Checkpoint cleared.")

    def _save(self, checkpoint: CheckpointData) -> None:
        """Save checkpoint to file."""
        with open(self.checkpoint_file, "w") as f:
            json.dump(asdict(checkpoint), f, indent=2)

    def print_status(self, checkpoint: CheckpointData) -> None:
        """Print checkpoint status."""
        print("\n" + "=" * 60)
        print("CHECKPOINT STATUS")
        print("=" * 60)
        print(f"Run ID:          {checkpoint.run_id}")
        print(f"Started:         {checkpoint.started_at}")
        print(f"Last Updated:    {checkpoint.last_updated}")
        print(f"Years:           {checkpoint.years}")
        print(f"Flow:            {checkpoint.flow_code}")
        print(f"Progress:        {checkpoint.completed_pairs}/{checkpoint.total_pairs} pairs")
        print(f"Records:         {checkpoint.total_records}")
        print(f"Failed pairs:    {len(checkpoint.failed_pairs)}")
        print(f"Output file:     {checkpoint.output_file}")
        print("=" * 60)
