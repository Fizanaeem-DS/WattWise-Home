"""Generate and validate the Stage 10 PV economics artifacts."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "stage7" / "backend"))

from hackowatt_stage10 import run  # noqa: E402


if __name__ == "__main__":
    summary = run()
    print("Stage 10 validation:", summary["validation"]["status"])
    print("Validation gates:", len(summary["validation"]["checks"]))
    print("Calculation SHA-256:", summary["determinism"]["calculation_sha256"])
