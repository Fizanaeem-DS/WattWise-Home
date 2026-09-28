"""Paths and exact column groups for the Stage 3C integration layer."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TIMEZONE = "Europe/Madrid"

STAGE2_INPUT = PROJECT_ROOT / "data" / "processed" / "stage2_barcelona_weather_solar_hourly.csv"
STAGE3A_INPUT = PROJECT_ROOT / "data" / "processed" / "stage3a_base_routine_hourly.csv"
STAGE3A_LEDGER = PROJECT_ROOT / "data" / "processed" / "stage3a_event_ledger.json"
STAGE3A_METADATA = PROJECT_ROOT / "data" / "processed" / "stage3a_metadata.json"
STAGE3B_INPUT = PROJECT_ROOT / "data" / "processed" / "stage3b_major_systems_hourly.csv"
STAGE3B_LEDGER = PROJECT_ROOT / "data" / "processed" / "stage3b_event_ledger.json"
STAGE3B_METADATA = PROJECT_ROOT / "data" / "processed" / "stage3b_metadata.json"

HOURLY_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage3c_household_hourly.csv"
METADATA_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage3c_metadata.json"
VALIDATION_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage3c_validation_report.json"

SOURCE_PATHS = {
    "stage2_hourly": STAGE2_INPUT,
    "stage3a_hourly": STAGE3A_INPUT,
    "stage3a_event_ledger": STAGE3A_LEDGER,
    "stage3a_metadata": STAGE3A_METADATA,
    "stage3b_hourly": STAGE3B_INPUT,
    "stage3b_event_ledger": STAGE3B_LEDGER,
    "stage3b_metadata": STAGE3B_METADATA,
}

WEATHER_COLUMNS = (
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "cloud_cover",
    "wind_speed_10m",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
)

STAGE3A_STATE_COLUMNS = (
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

STAGE3A_COMPONENT_COLUMNS = (
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

STAGE3B_STATE_COLUMNS = (
    "daily_stage3b_classification",
    "indoor_temperature_c",
    "effective_heating_target_c",
    "effective_cooling_target_c",
    "hvac_mode",
    "ev1_home",
    "ev2_home",
    "ev1_home_fraction",
    "ev2_home_fraction",
)

STAGE3B_COMPONENT_COLUMNS = (
    "heating_kwh",
    "cooling_kwh",
    "hvac_kwh",
    "ev1_charging_kwh",
    "ev2_charging_kwh",
    "ev_total_kwh",
    "pool_circulation_kwh",
    "pool_heating_kwh",
    "sauna_kwh",
)

CATEGORY_COLUMNS = (
    "base_fixed_kwh",
    "routine_behavior_kwh",
    "ev_kwh",
    "pool_kwh",
)

FINAL_ENERGY_COLUMNS = (
    *STAGE3A_COMPONENT_COLUMNS,
    "stage3a_total_kwh",
    *STAGE3B_COMPONENT_COLUMNS,
    "stage3b_total_kwh",
    *CATEGORY_COLUMNS,
    "household_total_kwh",
)
