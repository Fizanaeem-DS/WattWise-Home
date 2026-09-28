"""Paths and frozen analysis definitions for Stage 4."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGE3C_INPUT = PROJECT_ROOT / "data" / "processed" / "stage3c_household_hourly.csv"
STAGE3C_METADATA = PROJECT_ROOT / "data" / "processed" / "stage3c_metadata.json"
STAGE3C_VALIDATION = PROJECT_ROOT / "data" / "processed" / "stage3c_validation_report.json"
STAGE3A_LEDGER = PROJECT_ROOT / "data" / "processed" / "stage3a_event_ledger.json"
STAGE3B_LEDGER = PROJECT_ROOT / "data" / "processed" / "stage3b_event_ledger.json"
STAGE3B_METADATA = PROJECT_ROOT / "data" / "processed" / "stage3b_metadata.json"

METRICS_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage4_validation_metrics.json"
BASELINE_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage4_baseline_metrics.json"
REPORT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage4_validation_report.json"
FIGURES_DIR = PROJECT_ROOT / "artifacts" / "stage4_validation"

TRAIN_START = "2025-08-01T00:00:00+02:00"
TRAIN_END = "2025-08-31T23:00:00+02:00"
EVALUATION_START = "2025-09-01T00:00:00+02:00"
EVALUATION_END = "2025-09-30T23:00:00+02:00"

CATEGORY_COLUMNS = (
    "base_fixed_kwh",
    "routine_behavior_kwh",
    "hvac_kwh",
    "ev_kwh",
    "pool_kwh",
    "sauna_kwh",
)

LEAF_COMPONENT_COLUMNS = (
    "refrigerator_kwh",
    "smart_home_base_kwh",
    "cooking_kwh",
    "dishwasher_kwh",
    "washer_kwh",
    "dryer_kwh",
    "electronics_kwh",
    "phone_tablet_kwh",
    "interior_lighting_kwh",
    "exterior_security_lighting_kwh",
    "heating_kwh",
    "cooling_kwh",
    "ev1_charging_kwh",
    "ev2_charging_kwh",
    "pool_circulation_kwh",
    "pool_heating_kwh",
    "sauna_kwh",
)

ACTIVE_BEHAVIOR_COLUMNS = (
    "cooking_kwh",
    "dishwasher_kwh",
    "washer_kwh",
    "dryer_kwh",
    "electronics_kwh",
    "phone_tablet_kwh",
    "interior_lighting_kwh",
    "exterior_security_lighting_kwh",
    "sauna_kwh",
)

AUTONOMOUS_COLUMNS = (
    "refrigerator_kwh",
    "smart_home_base_kwh",
    "heating_kwh",
    "cooling_kwh",
    "pool_circulation_kwh",
    "pool_heating_kwh",
)
