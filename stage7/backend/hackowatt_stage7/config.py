"""Stage 7B paths and frozen-upstream identity."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STAGE3A_LEDGER = ROOT / "data" / "processed" / "stage3a_event_ledger.json"
STAGE3B_LEDGER = ROOT / "data" / "processed" / "stage3b_event_ledger.json"
STAGE3B_HOURLY = ROOT / "data" / "processed" / "stage3b_major_systems_hourly.csv"
STAGE3B_METADATA = ROOT / "data" / "processed" / "stage3b_metadata.json"
OUTPUT_PATH = ROOT / "stage7" / "artifacts" / "stage7b_optimization_requirements.json"
REPORT_PATH = ROOT / "stage7" / "artifacts" / "stage7b_validation_report.json"

# Hash of every pre-Stage-7B file under the frozen artifact/source roots.
FROZEN_UPSTREAM_FILE_COUNT = 172
FROZEN_UPSTREAM_TREE_SHA256 = "7223ec6131a68ff5f8b9f686aa22021aa3720d7013e079ecb46c164e7daeb8a3"

