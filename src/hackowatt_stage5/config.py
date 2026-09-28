"""Frozen Stage 5 paths, features, origin schedule, and model defaults."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGE3C_INPUT = PROJECT_ROOT / "data" / "processed" / "stage3c_household_hourly.csv"
STAGE4_METRICS = PROJECT_ROOT / "data" / "processed" / "stage4_validation_metrics.json"
STAGE4_BASELINES = PROJECT_ROOT / "data" / "processed" / "stage4_baseline_metrics.json"
STAGE4_REPORT = PROJECT_ROOT / "data" / "processed" / "stage4_validation_report.json"

PREDICTIONS_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage5_forecast_predictions.csv"
METRICS_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage5_model_metrics.json"
COMPARISON_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage5_baseline_comparison.json"
CONTRACT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage5_forecast_contract.json"
FIGURES_DIR = PROJECT_ROOT / "artifacts" / "stage5_forecasting"
MODEL_DIR = PROJECT_ROOT / "models" / "stage5"

FROZEN_STAGE3C_SHA256 = "fde362de6c8d758af02efe02110741e8c1bc352b6ed3030441038804a2a8c54a"
RANDOM_SEED = 20251002
HORIZONS = (24, 72, 168)
ORIGIN_START = "2025-09-01T23:00:00+02:00"
ORIGIN_STEP_HOURS = 72

WEATHER_FEATURES = (
    "temperature_2m",
    "relative_humidity_2m",
    "cloud_cover",
    "shortwave_radiation",
)

CALENDAR_FEATURES = (
    "hour_sin",
    "hour_cos",
    "weekday_sin",
    "weekday_cos",
    "is_weekend",
    "day_of_year_sin",
    "day_of_year_cos",
)

TARGET_HISTORY_FEATURES = (
    "lag_1h",
    "lag_2h",
    "lag_3h",
    "lag_24h",
    "lag_48h",
    "lag_168h",
    "trailing_mean_3h",
    "trailing_mean_6h",
    "trailing_mean_24h",
)

MODEL_SPECS = {
    "M1_GBT_CAL_WEATHER": {
        "model_type": "gradient_boosted_regression_trees",
        "feature_set": "calendar_weather",
        "hyperparameters": {
            "n_estimators": 40,
            "learning_rate": 0.05,
            "max_depth": 2,
            "min_samples_leaf": 20,
        },
    },
    "M2_GBT_HISTORY": {
        "model_type": "gradient_boosted_regression_trees",
        "feature_set": "calendar_weather_target_history",
        "hyperparameters": {
            "n_estimators": 40,
            "learning_rate": 0.05,
            "max_depth": 2,
            "min_samples_leaf": 20,
        },
    },
    "R2_RIDGE_HISTORY": {
        "model_type": "ridge_regression",
        "feature_set": "calendar_weather_target_history",
        "hyperparameters": {"alpha": 10.0},
    },
}

BASELINE_NAMES = (
    "B1_PREVIOUS_DAY",
    "B2_PREVIOUS_WEEK",
    "B3_HOUR_OF_WEEK_MEAN",
)

FORBIDDEN_FUTURE_PREDICTORS = (
    "household_total_kwh",
    "occupancy_state",
    "away",
    "guest_event",
    "hvac_mode",
    "indoor_temperature_c",
    "ev1_charging_kwh",
    "ev2_charging_kwh",
    "sauna_kwh",
    "pool_circulation_kwh",
    "pool_heating_kwh",
    "cooking_kwh",
    "dishwasher_kwh",
    "washer_kwh",
    "dryer_kwh",
    "electronics_kwh",
)
