"""Stage 9 frozen inputs, outputs, and deterministic solver constants."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGE3C_HOURLY = ROOT / "data/processed/stage3c_household_hourly.csv"
STAGE6B_FORECAST = ROOT / "data/processed/stage6b_forecast_explained.csv"
HOURLY_OUTPUT = ROOT / "data/processed/stage9_hourly_current_vs_optimized.csv"
EVENT_OUTPUT = ROOT / "data/processed/stage9_event_schedule.csv"
SUMMARY_OUTPUT = ROOT / "data/processed/stage9_optimizer_summary.json"
METHODOLOGY_DOC = ROOT / "docs/stage9_optimizer_methodology.md"
APP_CONTRACT_DOC = ROOT / "docs/stage9_app_contract.md"
FIGURES_DIR = ROOT / "artifacts/stage9"

TIMEZONE = "Europe/Madrid"
REFERENCE_CAPACITY_KWP = 5.0
EXPORT_PRICE_EUR_PER_KWH = 0.08
SCHEDULING_RESOLUTION_MINUTES = 15
COMFORT_TOLERANCE_C = 1e-6
# CBC's mixed-integer feasibility tolerance is larger than a sub-micro-euro
# post-optimality lock.  One hundred-thousandth of a euro (0.001 cent) is the
# numerical definition of "effectively equal cost" used only for the tertiary
# peak tie-break; it is not an economic trade-off tolerance.
COST_TOLERANCE_EUR = 1e-5
VALUE_TOLERANCE = 1e-7

FROZEN_UPSTREAM_FILE_COUNT = 212
FROZEN_UPSTREAM_TREE_SHA256 = "aff13b061666da33cf12363423827271268a4ea84906cf8085d719499b8bcb44"

FIXED_COLUMNS = (
    "refrigerator_kwh",
    "smart_home_base_kwh",
    "exterior_security_lighting_kwh",
)
BEHAVIORAL_COLUMNS = (
    "cooking_kwh",
    "electronics_kwh",
    "phone_tablet_kwh",
    "interior_lighting_kwh",
)

