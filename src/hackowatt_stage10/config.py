"""Frozen Stage 10 inputs, explicit assumptions, and output paths."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

CAPACITIES_KWP = (3.0, 5.0, 8.0, 10.0)
REFERENCE_CAPACITY_KWP = 5.0
INSTALLATION_COST_EUR_PER_KWP = 1300.0
ANNUAL_OM_FRACTION = 0.01
EXPORT_COMPENSATION_EUR_PER_KWH = 0.08
OBSERVED_DAYS = 61
ANNUAL_DAYS = 365
DEMAND_ANNUALIZATION_FACTOR = ANNUAL_DAYS / OBSERVED_DAYS
TIMEZONE = "Europe/Madrid"

STAGE8_HOURLY = ROOT / "data/processed/stage8_pv_hourly_per_kwp.csv"
STAGE8_EXAMPLES = ROOT / "data/processed/stage8_pv_capacity_examples.json"
STAGE9_HOURLY = ROOT / "data/processed/stage9_hourly_current_vs_optimized.csv"
STAGE9_SUMMARY = ROOT / "data/processed/stage9_optimizer_summary.json"

CAPACITY_COMPARISON_OUTPUT = ROOT / "data/processed/stage10_capacity_comparison.csv"
SUMMARY_OUTPUT = ROOT / "data/processed/stage10_economics_summary.json"
AUG_SEP_OUTPUT = ROOT / "data/processed/stage10_aug_sep_validation.csv"
ANNUALIZED_OUTPUT = ROOT / "data/processed/stage10_annualized_comparison.csv"
METHODOLOGY_DOC = ROOT / "docs/stage10_economics_methodology.md"
FIGURES_DIR = ROOT / "artifacts/stage10"

FROZEN_STAGE1_TO_STAGE9_FILE_COUNT = 1249
FROZEN_STAGE1_TO_STAGE9_TREE_SHA256 = "5b22f596fc12fd16390f2bac8c871a6e9e632fa7b81cecb8988d601df84ba214"
FROZEN_FILE_SHA256 = {
    "data/processed/stage8_pv_hourly_per_kwp.csv": "525e4387208280f6ea137c73303fdfeff5a0dea7dcfd217e9a992f8bbcb0dd66",
    "data/processed/stage8_pv_capacity_examples.json": "4df061d1a829cf9d80a4010248288cc189fe7ea70e53cd1f8e24c9cc5d33635b",
    "data/processed/stage9_hourly_current_vs_optimized.csv": "d4014c03066e77c8373daed4991861480d7aae7b9950dd9a7a29ed60c0aad0f8",
    "src/hackowatt_stage9/accounting.py": "ef52fb36221ee4af7c3d90dc2fcf88a7660fd65abd2e3f471c018f5730602a9a",
    "src/hackowatt_stage9/data.py": "e34016920eaf8eb276b7e6516e8e7f7e5939ee5f66d4602bd66b1d645eba3bd1",
}
