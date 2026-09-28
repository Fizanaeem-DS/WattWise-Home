"""Fixed paths, seeds, and frozen fingerprints for Stage 6A."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGE2_INPUT = PROJECT_ROOT / "data" / "processed" / "stage2_barcelona_weather_solar_hourly.csv"
STAGE3C_INPUT = PROJECT_ROOT / "data" / "processed" / "stage3c_household_hourly.csv"
STAGE4_METRICS = PROJECT_ROOT / "data" / "processed" / "stage4_validation_metrics.json"
STAGE4_BASELINES = PROJECT_ROOT / "data" / "processed" / "stage4_baseline_metrics.json"
STAGE4_REPORT = PROJECT_ROOT / "data" / "processed" / "stage4_validation_report.json"
STAGE5_PREDICTIONS = PROJECT_ROOT / "data" / "processed" / "stage5_forecast_predictions.csv"
STAGE5_METRICS = PROJECT_ROOT / "data" / "processed" / "stage5_model_metrics.json"
STAGE5_COMPARISON = PROJECT_ROOT / "data" / "processed" / "stage5_baseline_comparison.json"
STAGE5_CONTRACT = PROJECT_ROOT / "data" / "processed" / "stage5_forecast_contract.json"

HOURLY_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage6a_peak_risk_hourly.csv"
METRICS_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage6a_peak_risk_metrics.json"
DIAGNOSTICS_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage6a_peak_diagnostics.csv"
CALIBRATION_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage6a_calibration.csv"
ENSEMBLE_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage6a_ensemble_demand.npy"
FIGURES_DIR = PROJECT_ROOT / "artifacts" / "stage6a"

ENSEMBLE_SIZE = 200
SEED_BASE = 6_100_000
PEAK_PERCENTILE = 90.0
HORIZONS = (24, 72, 168)
SELECTED_STAGE5_BY_HORIZON = {
    24: "M2_GBT_HISTORY",
    72: "M1_GBT_CAL_WEATHER",
    168: "M1_GBT_CAL_WEATHER",
}
PROBLEM_WINDOW_ORIGIN = "2025-09-13T23:00:00+02:00"

FROZEN_STAGE3C_SHA256 = "fde362de6c8d758af02efe02110741e8c1bc352b6ed3030441038804a2a8c54a"
FROZEN_STAGE4_SHA256 = {
    "validation_metrics": "ab42b583a8de26731ba2bc80be04582f27d29a79cccb8600c5f1023422a02417",
    "baseline_metrics": "b7d377b4b176f4b7d0ebefa09d7ab4d5dfb3f4e2fd8683ff4e9777d8d4e3fc12",
    "validation_report": "cbeb57f269439960fb3b91f4ddb095f35e63e1e64ad7372635eadb08b4651878",
}
FROZEN_STAGE5_SHA256 = {
    "predictions": "3892770ff779efe4b9ea64b23604076b8b0341086361dbf2d1a27c0857e4d76d",
    "metrics": "4f2b4e16b2c568bfe7b605b944ec6496c3b8c4b63e70c0e40d22cca2f820c6b6",
    "comparison": "fa733505f2c60a7b6234f2e02b916e0c5540685d20206b4350bd61289600a5e8",
    "contract": "74cbed58c6695464c1930df2b2d6b4fec3c87263936052b29356c1c12350b96d",
}
FROZEN_STAGE5_FULL_MANIFEST_SHA256 = "7ab4a40c8d5a837e4083fe474a6988603cb4f0fb4d14872db750d26c12357577"
FROZEN_STAGE5B_CORE_SHA256 = {
    "predictions": "29041fde17317701265ee2fd86f4a104670838e0f40f3a7e6ef4583d6ff70a8e",
    "metrics": "3ceae32121ae805c0a4c90eee625da8fa1c9209686fd937bf1d350317d5a9fa7",
    "comparison": "75584b82948d56ecc065ae8181cd2071ccbcd3d5cd0501f86734971f3a57fe8c",
    "diagnostics": "64ee678b25e06bcc0d424b58206a819afed81e0a5593d99007336ef31d67c5f9",
    "figure": "83920eae440b69354b95cb66b22c439dc7a6fdbc75bf5855cbe1d6a9a41f9858",
}
FROZEN_STAGE5B_MANIFEST_SHA256 = "ceb7fcb8ee9f0d823be518f0807577c7bf9f2470bc595fa53b875f36379592b8"
FROZEN_UPSTREAM_MANIFEST_SHA256 = "365b1d4e3f4e3ed8b37317408202472969d24bd0c73ebbfb50deadee781f5c3a"


def member_seeds(member_index: int) -> tuple[int, int]:
    """Independent deterministic Stage 3A/3B seeds for a zero-based member."""
    return SEED_BASE + 2 * member_index, SEED_BASE + 2 * member_index + 1

