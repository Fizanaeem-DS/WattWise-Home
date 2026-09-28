"""Run the deterministic Stage 9 optimizer and validation pipeline."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "stage7" / "backend"))

from hackowatt_stage9.pipeline import run  # noqa: E402


if __name__ == "__main__":
    summary = run(verify_determinism=True)
    totals = summary["aug_sep"]
    print("Stage 9 validation:", summary["validation"]["status"])
    print("Current net cost (EUR):", totals["current_net_electricity_cost_eur"])
    print("Optimized net cost (EUR):", totals["optimized_net_electricity_cost_eur"])
    print("Schedule SHA-256:", summary["determinism"]["schedule_sha256"])
