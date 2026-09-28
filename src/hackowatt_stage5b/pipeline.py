"""Run the separate Stage 5B experiment without changing the frozen Stage 5 benchmark."""

from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from hackowatt_stage4.figures import line_chart
from hackowatt_stage5.config import FORBIDDEN_FUTURE_PREDICTORS, HORIZONS, WEATHER_FEATURES
from hackowatt_stage5.forecasting import feature_names, origin_schedule, read_profile

from .config import (
    CLASSIFIER_PARAMETERS,
    COMPARATORS_BY_HORIZON,
    COMPARISON_OUTPUT,
    DIAGNOSTICS_OUTPUT,
    FIGURES_DIR,
    FROZEN_STAGE3C_SHA256,
    FROZEN_STAGE4_SHA256,
    FROZEN_STAGE5_FULL_MANIFEST_SHA256,
    FROZEN_STAGE5_SHA256,
    HIGH_DEMAND_PERCENTILE,
    METRICS_OUTPUT,
    MODEL_DIR,
    MODEL_NAME,
    PREDICTIONS_OUTPUT,
    PROBLEM_WINDOW_ORIGIN,
    PROJECT_ROOT,
    REGRESSOR_PARAMETERS,
    SELECTED_STAGE5_BY_HORIZON,
    STAGE3C_INPUT,
    STAGE4_BASELINES,
    STAGE4_METRICS,
    STAGE4_REPORT,
    STAGE5_COMPARISON,
    STAGE5_CONTRACT,
    STAGE5_METRICS,
    STAGE5_PREDICTIONS,
)
from .experiment import (
    evaluation_bundle,
    fit_peak_aware,
    peak_diagnostic_rows,
    recursive_peak_aware_forecast,
)


ACCEPTANCE_CLASSIFICATION = "NO USEFUL IMPROVEMENT"
ACCEPTANCE_EVIDENCE = (
    "Stage 5B raises high-demand recall at all horizons and reduces peak-magnitude error at 72h and 168h, "
    "but WAPE, MAE, RMSE, and period-energy error are materially worse at every horizon; peak overlap is lower "
    "at every horizon, and high-demand F1 is lower at 72h and 168h. The candidate therefore does not justify "
    "replacement of any frozen Stage 5 selection."
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage5_manifest() -> tuple[str, dict[str, str]]:
    files = sorted(
        [
            *PROJECT_ROOT.glob("data/processed/stage5_*"),
            *PROJECT_ROOT.glob("models/stage5/**/*"),
            *PROJECT_ROOT.glob("artifacts/stage5_forecasting/**/*"),
        ]
    )
    fingerprints = {
        path.relative_to(PROJECT_ROOT).as_posix(): sha256(path)
        for path in files
        if path.is_file()
    }
    manifest_text = "".join(f"{path}\t{digest}\n" for path, digest in fingerprints.items())
    return hashlib.sha256(manifest_text.encode("utf-8")).hexdigest(), fingerprints


def frozen_fingerprints() -> dict[str, Any]:
    manifest_hash, manifest = stage5_manifest()
    return {
        "stage3c": sha256(STAGE3C_INPUT),
        "stage4": {
            "validation_metrics": sha256(STAGE4_METRICS),
            "baseline_metrics": sha256(STAGE4_BASELINES),
            "validation_report": sha256(STAGE4_REPORT),
        },
        "stage5_core": {
            "predictions": sha256(STAGE5_PREDICTIONS),
            "metrics": sha256(STAGE5_METRICS),
            "comparison": sha256(STAGE5_COMPARISON),
            "contract": sha256(STAGE5_CONTRACT),
        },
        "stage5_full_manifest_sha256": manifest_hash,
        "stage5_manifest_file_count": len(manifest),
        "stage5_manifest": manifest,
    }


def assert_frozen(fingerprints: dict[str, Any]) -> None:
    if fingerprints["stage3c"] != FROZEN_STAGE3C_SHA256:
        raise RuntimeError("STOP: frozen Stage 3C fingerprint changed")
    if fingerprints["stage4"] != FROZEN_STAGE4_SHA256:
        raise RuntimeError("STOP: frozen Stage 4 fingerprints changed")
    if fingerprints["stage5_core"] != FROZEN_STAGE5_SHA256:
        raise RuntimeError("STOP: frozen Stage 5 core fingerprints changed")
    if fingerprints["stage5_full_manifest_sha256"] != FROZEN_STAGE5_FULL_MANIFEST_SHA256:
        raise RuntimeError("STOP: frozen Stage 5 model/output/figure manifest changed")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _save_origin_model(models: dict[str, Any], audit: dict[str, Any]) -> str:
    origin = datetime.fromisoformat(audit["origin"])
    stamp = origin.strftime("%Y%m%dT%H%M%S%z")
    path = MODEL_DIR / "evaluation" / f"{stamp}_{MODEL_NAME}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stage": "5B - controlled peak-aware forecasting experiment",
        "status": "EXPERIMENT_NOT_PROMOTED",
        "model_name": MODEL_NAME,
        "training_audit": audit,
        "feature_set": "calendar_weather_target_history",
        "feature_names": feature_names("calendar_weather_target_history"),
        "threshold_rule": f"{HIGH_DEMAND_PERCENTILE:g}th percentile of household_total_kwh observed at or before origin",
        "classifier": models["classifier"].to_dict(),
        "normal_regime_regressor": models["normal_regressor"].to_dict(),
        "high_regime_regressor": models["high_regressor"].to_dict(),
        "combination_rule": "(1 - p_high) * normal_prediction + p_high * high_prediction; then max(0, result)",
        "recursive_rule": "Observed household target history through origin; Stage 5B predictions thereafter.",
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path.relative_to(PROJECT_ROOT).as_posix()


def _convert_frozen_record(row: dict[str, str], threshold: float) -> dict[str, Any]:
    return {
        "timestamp": row["timestamp"],
        "forecast_origin": row["forecast_origin"],
        "lead_hour": int(row["lead_hour"]),
        "predicted_household_kwh": float(row["predicted_household_kwh"]),
        "actual_household_kwh": float(row["actual_household_kwh"]),
        "high_demand_threshold_kwh": threshold,
    }


def _metric_differences(candidate: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, float]:
    candidate_load = candidate["load_period_peak_metrics"]
    benchmark_load = benchmark["load_period_peak_metrics"]
    candidate_high = candidate["high_demand_metrics"]
    benchmark_high = benchmark["high_demand_metrics"]
    return {
        "mae_kwh_change": round(candidate_load["mae_kwh"] - benchmark_load["mae_kwh"], 9),
        "rmse_kwh_change": round(candidate_load["rmse_kwh"] - benchmark_load["rmse_kwh"], 9),
        "wape_percentage_point_change": round(candidate_load["wape_percent"] - benchmark_load["wape_percent"], 9),
        "period_total_mape_percentage_point_change": round(candidate_load["period_total_mape_percent"] - benchmark_load["period_total_mape_percent"], 9),
        "period_total_signed_bias_percentage_point_change": round(candidate_load["period_total_mean_signed_bias_percent"] - benchmark_load["period_total_mean_signed_bias_percent"], 9),
        "peak_overlap_percentage_point_change": round(candidate_load["peak_overlap_percent"] - benchmark_load["peak_overlap_percent"], 9),
        "peak_magnitude_mae_kwh_change": round(candidate_load["peak_magnitude_mae_kwh"] - benchmark_load["peak_magnitude_mae_kwh"], 9),
        "high_demand_precision_change": round(candidate_high["precision"] - benchmark_high["precision"], 9),
        "high_demand_recall_change": round(candidate_high["recall"] - benchmark_high["recall"], 9),
        "high_demand_f1_change": round(candidate_high["f1"] - benchmark_high["f1"], 9),
    }


def _problem_window_figure(
    stage5b: list[dict[str, Any]], frozen_lookup: dict[tuple[int, str, str, str], dict[str, Any]]
) -> dict[str, Any]:
    window = sorted(
        [record for record in stage5b if record["forecast_origin"] == PROBLEM_WINDOW_ORIGIN],
        key=lambda record: record["lead_hour"],
    )
    if len(window) != 168:
        raise RuntimeError("STOP: exact Stage 5 Sep-13 168h comparison window cannot be reproduced")
    frozen = [
        frozen_lookup[(168, record["forecast_origin"], record["timestamp"], "M1_GBT_CAL_WEATHER")]
        for record in window
    ]
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / "168h_problem_window_comparison.svg"
    line_chart(
        path,
        "Sep-13 168h problem window: actual, frozen M1, and Stage 5B",
        [
            ("Actual", [record["actual_household_kwh"] for record in window]),
            ("Frozen M1", [record["predicted_household_kwh"] for record in frozen]),
            ("Stage 5B", [record["predicted_household_kwh"] for record in window]),
        ],
        [datetime.fromisoformat(record["timestamp"]).strftime("%b %d %H:%M") for record in window],
        "kWh per hour",
    )
    actual_max = max(record["actual_household_kwh"] for record in window)
    frozen_max = max(record["predicted_household_kwh"] for record in frozen)
    candidate_max = max(record["predicted_household_kwh"] for record in window)
    return {
        "forecast_origin": PROBLEM_WINDOW_ORIGIN,
        "actual_max_kwh": actual_max,
        "frozen_m1_max_kwh": frozen_max,
        "stage5b_max_kwh": candidate_max,
        "frozen_m1_peak_magnitude_absolute_error_kwh": abs(actual_max - frozen_max),
        "stage5b_peak_magnitude_absolute_error_kwh": abs(actual_max - candidate_max),
        "figure": path.relative_to(PROJECT_ROOT).as_posix(),
    }


def main() -> int:
    before = frozen_fingerprints()
    assert_frozen(before)
    profile = read_profile()
    schedules = origin_schedule(profile)
    unique_origins = sorted({origin for origins in schedules.values() for origin in origins})
    records_by_horizon: dict[int, list[dict[str, Any]]] = {horizon: [] for horizon in HORIZONS}
    training_audits: dict[str, dict[str, Any]] = {}
    model_artifacts: dict[str, str] = {}

    for origin in unique_origins:
        applicable = [horizon for horizon, origins in schedules.items() if origin in origins]
        models, audit = fit_peak_aware(profile, origin)
        training_audits[origin.isoformat()] = audit
        model_artifacts[origin.isoformat()] = _save_origin_model(models, audit)
        forecast = recursive_peak_aware_forecast(
            profile,
            origin,
            max(applicable),
            models,
            audit["high_demand_threshold_kwh"],
        )
        for horizon in applicable:
            for record in forecast[:horizon]:
                records_by_horizon[horizon].append(
                    {
                        "timestamp": record["timestamp"],
                        "forecast_origin": record["forecast_origin"],
                        "horizon_hours": horizon,
                        "lead_hour": record["lead_hour"],
                        "model": MODEL_NAME,
                        "feature_set": "calendar_weather_target_history",
                        **{key: value for key, value in record.items() if key not in {"timestamp", "forecast_origin", "lead_hour"}},
                    }
                )

    all_records = [record for horizon in HORIZONS for record in records_by_horizon[horizon]]
    _write_csv(PREDICTIONS_OUTPUT, all_records)

    thresholds = {
        origin: audit["high_demand_threshold_kwh"]
        for origin, audit in training_audits.items()
    }
    frozen_rows = _read_csv(STAGE5_PREDICTIONS)
    frozen_lookup: dict[tuple[int, str, str, str], dict[str, Any]] = {}
    for row in frozen_rows:
        horizon = int(row["horizon_hours"])
        key = (horizon, row["forecast_origin"], row["timestamp"], row["model"])
        frozen_lookup[key] = _convert_frozen_record(row, thresholds[row["forecast_origin"]])

    candidate_metrics = {
        str(horizon): evaluation_bundle(records_by_horizon[horizon]) for horizon in HORIZONS
    }
    comparison_by_horizon: dict[str, Any] = {}
    for horizon in HORIZONS:
        reference_keys = {
            (record["forecast_origin"], record["timestamp"])
            for record in records_by_horizon[horizon]
        }
        comparator_metrics: dict[str, Any] = {}
        for model_name in COMPARATORS_BY_HORIZON[horizon]:
            records = [
                frozen_lookup[(horizon, origin, timestamp, model_name)]
                for origin, timestamp in sorted(reference_keys)
            ]
            comparator_metrics[model_name] = evaluation_bundle(records)
        selected_name = SELECTED_STAGE5_BY_HORIZON[horizon]
        comparison_by_horizon[str(horizon)] = {
            "timestamp_identity_confirmed": all(
                len(reference_keys) == len(records_by_horizon[horizon])
                for _ in COMPARATORS_BY_HORIZON[horizon]
            ),
            "frozen_selected_model": selected_name,
            "stage5b": candidate_metrics[str(horizon)],
            "frozen_comparators": comparator_metrics,
            "stage5b_difference_vs_frozen_selected": _metric_differences(
                candidate_metrics[str(horizon)], comparator_metrics[selected_name]
            ),
            "stage5b_difference_vs_b3": _metric_differences(
                candidate_metrics[str(horizon)], comparator_metrics["B3_HOUR_OF_WEEK_MEAN"]
            ),
        }

    diagnostics = peak_diagnostic_rows(records_by_horizon, frozen_lookup, SELECTED_STAGE5_BY_HORIZON)
    _write_csv(DIAGNOSTICS_OUTPUT, diagnostics)
    problem_window = _problem_window_figure(records_by_horizon[168], frozen_lookup)

    after = frozen_fingerprints()
    assert_frozen(after)
    if before != after:
        raise RuntimeError("STOP: frozen upstream artifact inventory changed during Stage 5B")

    metrics_payload = {
        "stage": "5B - controlled peak-aware forecasting experiment",
        "status": "EXPERIMENT_NOT_PROMOTED",
        "stage6_started": False,
        "frozen_upstream_unchanged": True,
        "frozen_upstream_fingerprints_before_and_after": after,
        "method": {
            "threshold": f"Per-origin {HIGH_DEMAND_PERCENTILE:g}th percentile of household_total_kwh observed at or before forecast origin.",
            "classifier": "Deterministic unweighted L2 logistic regression with fixed settings; no hyperparameter search.",
            "classifier_parameters": CLASSIFIER_PARAMETERS,
            "normal_regime_regressor": "Deterministic gradient-boosted regression trees trained only on below-threshold observations.",
            "high_regime_regressor": "Deterministic gradient-boosted regression trees trained only on at/above-threshold observations.",
            "regressor_parameters": REGRESSOR_PARAMETERS,
            "combination": "(1 - p_high) * normal_prediction + p_high * high_prediction, clipped to >= 0.",
            "feature_names": feature_names("calendar_weather_target_history"),
            "allowed_future_weather": WEATHER_FEATURES,
            "forbidden_future_predictors": FORBIDDEN_FUTURE_PREDICTORS,
            "recursive_history": "Observed household_total_kwh through origin; previous Stage 5B predictions after origin; never actual post-origin demand.",
            "high_demand_evaluation_rule": "Actual and predicted load are high when each is >= the threshold learned at that forecast origin.",
        },
        "origin_schedule": {
            str(horizon): [origin.isoformat() for origin in origins]
            for horizon, origins in schedules.items()
        },
        "training_by_origin": training_audits,
        "threshold_range_kwh": {
            "minimum": min(thresholds.values()),
            "maximum": max(thresholds.values()),
        },
        "high_regime_training_sample_range": {
            "minimum": min(audit["high_regime_training_observations"] for audit in training_audits.values()),
            "maximum": max(audit["high_regime_training_observations"] for audit in training_audits.values()),
        },
        "metrics_by_horizon": candidate_metrics,
        "problem_window": problem_window,
        "model_artifacts": model_artifacts,
        "acceptance_classification": ACCEPTANCE_CLASSIFICATION,
        "acceptance_evidence": ACCEPTANCE_EVIDENCE,
        "promotion_recommendation": "Do not promote Stage 5B; retain the frozen Stage 5 selected models.",
    }
    METRICS_OUTPUT.write_text(json.dumps(metrics_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    comparison_payload = {
        "scope": "Stage 5B, frozen selected/M1-or-M2, and B3 use identical origin/timestamp forecast instances within each horizon.",
        "by_horizon": comparison_by_horizon,
        "worst_peak_diagnostic_rows": len(diagnostics),
        "problem_window": problem_window,
        "acceptance_classification": ACCEPTANCE_CLASSIFICATION,
        "acceptance_evidence": ACCEPTANCE_EVIDENCE,
        "stage5_replaced": False,
    }
    COMPARISON_OUTPUT.write_text(json.dumps(comparison_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "origins": len(unique_origins),
                "prediction_rows": len(all_records),
                "threshold_range_kwh": metrics_payload["threshold_range_kwh"],
                "high_training_sample_range": metrics_payload["high_regime_training_sample_range"],
                "frozen_upstream_unchanged": True,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

