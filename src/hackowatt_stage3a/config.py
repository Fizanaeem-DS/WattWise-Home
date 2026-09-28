"""Frozen paths, seed, schema, and component names for Stage 3A."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RANDOM_SEED = 20250930
TIMEZONE = "Europe/Madrid"

STAGE2_INPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "stage2_barcelona_weather_solar_hourly.csv"
)
HOURLY_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "stage3a_base_routine_hourly.csv"
)
EVENT_LEDGER_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "stage3a_event_ledger.json"
)
METADATA_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "stage3a_metadata.json"
)
VALIDATION_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "stage3a_validation_report.json"
)

COMPONENT_COLUMNS = (
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
)

STATE_COLUMNS = (
    "timestamp",
    "day_type",
    "base_day_type",
    "is_weekend",
    "daytime_occupancy_state",
    "occupancy_state",
    "away",
    "away_event_id",
    "guest_event",
    "guest_event_id",
    "household_departure",
    "household_return",
)

MAJOR_SYSTEM_NAMES = (
    "hvac",
    "ev1",
    "ev2",
    "pool_circulation",
    "pool_heating",
    "sauna",
)

