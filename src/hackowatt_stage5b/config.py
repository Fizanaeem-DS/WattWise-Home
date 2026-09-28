"""Paths and fixed technical choices for the controlled Stage 5B experiment."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGE3C_INPUT = PROJECT_ROOT / "data" / "processed" / "stage3c_household_hourly.csv"
STAGE4_METRICS = PROJECT_ROOT / "data" / "processed" / "stage4_validation_metrics.json"
STAGE4_BASELINES = PROJECT_ROOT / "data" / "processed" / "stage4_baseline_metrics.json"
STAGE4_REPORT = PROJECT_ROOT / "data" / "processed" / "stage4_validation_report.json"
STAGE5_PREDICTIONS = PROJECT_ROOT / "data" / "processed" / "stage5_forecast_predictions.csv"
STAGE5_METRICS = PROJECT_ROOT / "data" / "processed" / "stage5_model_metrics.json"
STAGE5_COMPARISON = PROJECT_ROOT / "data" / "processed" / "stage5_baseline_comparison.json"
STAGE5_CONTRACT = PROJECT_ROOT / "data" / "processed" / "stage5_forecast_contract.json"

PREDICTIONS_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage5b_peak_aware_predictions.csv"
METRICS_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage5b_peak_aware_metrics.json"
COMPARISON_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage5b_comparison.json"
DIAGNOSTICS_OUTPUT = PROJECT_ROOT / "data" / "processed" / "stage5b_peak_miss_diagnostics.csv"
FIGURES_DIR = PROJECT_ROOT / "artifacts" / "stage5b"
MODEL_DIR = PROJECT_ROOT / "models" / "stage5b"

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

MODEL_NAME = "STAGE5B_PEAK_AWARE"
HIGH_DEMAND_PERCENTILE = 90.0
MINIMUM_HIGH_REGIME_TRAINING_SAMPLES = 40
CLASSIFIER_PARAMETERS = {
    "alpha": 1.0,
    "max_iterations": 50,
    "tolerance": 1e-10,
    "class_weight": "none",
}
REGRESSOR_PARAMETERS = {
    "normal": {
        "n_estimators": 40,
        "learning_rate": 0.05,
        "max_depth": 2,
        "min_samples_leaf": 20,
    },
    "high": {
        "n_estimators": 40,
        "learning_rate": 0.05,
        "max_depth": 2,
        "min_samples_leaf": 8,
    },
}

SELECTED_STAGE5_BY_HORIZON = {
    24: "M2_GBT_HISTORY",
    72: "M1_GBT_CAL_WEATHER",
    168: "M1_GBT_CAL_WEATHER",
}
COMPARATORS_BY_HORIZON = {
    24: ("M2_GBT_HISTORY", "M1_GBT_CAL_WEATHER", "B3_HOUR_OF_WEEK_MEAN"),
    72: ("M1_GBT_CAL_WEATHER", "M2_GBT_HISTORY", "B3_HOUR_OF_WEEK_MEAN"),
    168: ("M1_GBT_CAL_WEATHER", "M2_GBT_HISTORY", "B3_HOUR_OF_WEEK_MEAN"),
}
PROBLEM_WINDOW_ORIGIN = "2025-09-13T23:00:00+02:00"

