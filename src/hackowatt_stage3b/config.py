"""Paths and reproducibility settings for Stage 3B."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RANDOM_SEED = 20251001
TIMEZONE = "Europe/Madrid"

STAGE2_INPUT = PROJECT_ROOT / "data" / "processed" / "stage2_barcelona_weather_solar_hourly.csv"
STAGE3A_INPUT = PROJECT_ROOT / "data" / "processed" / "stage3a_base_routine_hourly.csv"
STAGE3A_LEDGER = PROJECT_ROOT / "data" / "processed" / "stage3a_event_ledger.json"
STAGE3A_METADATA = PROJECT_ROOT / "data" / "processed" / "stage3a_metadata.json"

HOURLY_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage3b_major_systems_hourly.csv"
EVENT_LEDGER_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage3b_event_ledger.json"
METADATA_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage3b_metadata.json"
VALIDATION_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage3b_validation_report.json"

ENERGY_COLUMNS = (
    "heating_kwh",
    "cooling_kwh",
    "ev1_charging_kwh",
    "ev2_charging_kwh",
    "pool_circulation_kwh",
    "pool_heating_kwh",
    "sauna_kwh",
)

