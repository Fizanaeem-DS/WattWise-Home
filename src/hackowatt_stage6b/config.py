"""Frozen inputs and output paths for Stage 6B."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGE2_INPUT = PROJECT_ROOT / "data" / "processed" / "stage2_barcelona_weather_solar_hourly.csv"
STAGE5_PREDICTIONS = PROJECT_ROOT / "data" / "processed" / "stage5_forecast_predictions.csv"
STAGE6A_HOURLY = PROJECT_ROOT / "data" / "processed" / "stage6a_peak_risk_hourly.csv"
STAGE6A_METRICS = PROJECT_ROOT / "data" / "processed" / "stage6a_peak_risk_metrics.json"

EXPLAINED_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage6b_forecast_explained.csv"
SUMMARIES_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage6b_forecast_summaries.json"
FIGURES_DIR = PROJECT_ROOT / "artifacts" / "stage6b"

PROBLEM_WINDOW_ORIGIN = "2025-09-13T23:00:00+02:00"
PROVENANCE_VALUE = "real"

FROZEN_STAGE6A_MANIFEST_SHA256 = "6f06c0f1b4ad7d9f4db0db1ed90aa7316f3a952b38740f717149790713b7cfd4"
FROZEN_STAGE1_TO_STAGE6A_MANIFEST_SHA256 = "b810dae0af8be25c8d2386190497857677ad275b60e3f56cadb9d13987a18e40"

OUTPUT_COLUMNS = (
    "timestamp",
    "forecast_origin",
    "horizon_hours",
    "lead_hour",
    "stage5_selected_model",
    "point_forecast_kwh",
    "p10_kwh",
    "p50_kwh",
    "p90_kwh",
    "p95_kwh",
    "peak_threshold_kwh",
    "peak_probability",
    "peak_risk_label",
    "temperature_2m",
    "is_weekend",
    "behavioral_block",
    "tariff_eur_per_kwh",
    "tariff_period",
    "primary_explanation",
    "secondary_explanation",
    "point_forecast_source",
    "risk_quantile_source",
    "explanation_source",
    "provenance",
)

