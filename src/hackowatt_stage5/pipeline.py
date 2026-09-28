"""Evaluate Stage 5 candidates and compatible baselines on rolling origins."""

from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
import statistics
from typing import Any

from hackowatt_stage4.figures import bar_chart, line_chart

from .config import (
    BASELINE_NAMES,
    CALENDAR_FEATURES,
    COMPARISON_OUTPUT,
    CONTRACT_OUTPUT,
    FIGURES_DIR,
    FORBIDDEN_FUTURE_PREDICTORS,
    FROZEN_STAGE3C_SHA256,
    HORIZONS,
    METRICS_OUTPUT,
    MODEL_DIR,
    MODEL_SPECS,
    PREDICTIONS_OUTPUT,
    RANDOM_SEED,
    STAGE3C_INPUT,
    STAGE4_BASELINES,
    STAGE4_METRICS,
    STAGE4_REPORT,
    TARGET_HISTORY_FEATURES,
    WEATHER_FEATURES,
)
from .forecasting import (
    aggregate_metrics,
    baseline_forecasts,
    feature_names,
    fit_candidate,
    origin_schedule,
    read_profile,
    recursive_forecast,
    sha256,
)


SELECTED_MODEL_BY_HORIZON = {
    24: "M2_GBT_HISTORY",
    72: "M1_GBT_CAL_WEATHER",
    168: "M1_GBT_CAL_WEATHER",
}

SELECTION_REASONS = {
    "24": "M2 has the lowest WAPE and MAE, lowest period-total MAPE and absolute bias, and highest peak overlap among candidates. M1 has slightly better RMSE and peak-magnitude MAE, but the broader evidence favors M2 for 24h.",
    "72": "M1 has the lowest candidate WAPE, MAE, RMSE, and period-total MAPE with near-zero aggregate period bias. R2 has higher peak overlap, but materially worse hourly and total-energy errors.",
    "168": "M1 has the lowest candidate WAPE, MAE, RMSE, period-total MAPE, and smaller peak-magnitude error than the other learned candidates. M2 has higher peak overlap but accumulates substantial recursive underprediction bias.",
}


def _artifact_path(origin: datetime, model_name: str) -> Path:
    stamp = origin.strftime("%Y%m%dT%H%M%S%z")
    return MODEL_DIR / "evaluation" / f"{stamp}_{model_name}.json"


def _save_model_artifact(
    path: Path,
    model_name: str,
    model,
    cutoff: datetime,
    training_observations: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stage": "5 - household electricity demand forecasting",
        "model_name": model_name,
        "training_cutoff": cutoff.isoformat(),
        "training_observations": training_observations,
        "feature_set": MODEL_SPECS[model_name]["feature_set"],
        "feature_names": feature_names(MODEL_SPECS[model_name]["feature_set"]),
        "forecasting_strategy": "recursive one-step; predicted targets replace unavailable actual future target history",
        "non_negative_rule": "max(0, raw_prediction)",
        "model": model.to_dict(),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _enrich_record(
    record: dict[str, Any],
    horizon: int,
    row_by_timestamp: dict[str, dict[str, str]],
) -> dict[str, Any]:
    source = row_by_timestamp[record["timestamp"]]
    timestamp = datetime.fromisoformat(record["timestamp"])
    model_name = record["model"]
    feature_set = (
        MODEL_SPECS[model_name]["feature_set"] if model_name in MODEL_SPECS else "compatible_simple_baseline"
    )
    return {
        "timestamp": record["timestamp"],
        "forecast_origin": record["forecast_origin"],
        "horizon_hours": horizon,
        "lead_hour": record["lead_hour"],
        "model": model_name,
        "feature_set": feature_set,
        "predicted_household_kwh": record["predicted_household_kwh"],
        "actual_household_kwh": record["actual_household_kwh"],
        "temperature_2m": source["temperature_2m"],
        "relative_humidity_2m": source["relative_humidity_2m"],
        "cloud_cover": source["cloud_cover"],
        "shortwave_radiation": source["shortwave_radiation"],
        "forecast_hour": timestamp.hour,
        "forecast_weekday": timestamp.weekday(),
        "forecast_is_weekend": timestamp.weekday() >= 5,
        "prediction_clipped_to_zero": record["prediction_clipped_to_zero"],
        "maximum_actual_target_reference": record["maximum_actual_target_reference"],
        "recursive_prediction_reference_count": record["recursive_prediction_reference_count"],
        "actual_future_target_used": record["actual_future_target_used"],
        "future_exogenous_source": "realized_stage2_weather_perfect_weather_proxy",
    }


def _comparison(metrics: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for horizon in HORIZONS:
        horizon_metrics = metrics[str(horizon)]
        strongest_name = min(BASELINE_NAMES, key=lambda name: horizon_metrics[name]["wape_percent"])
        strongest = horizon_metrics[strongest_name]
        candidates = {}
        for name in MODEL_SPECS:
            candidate = horizon_metrics[name]
            candidates[name] = {
                "wape_relative_improvement_percent": round((strongest["wape_percent"] - candidate["wape_percent"]) / strongest["wape_percent"] * 100, 9),
                "wape_percentage_point_difference": round(strongest["wape_percent"] - candidate["wape_percent"], 9),
                "mae_relative_improvement_percent": round((strongest["mae_kwh"] - candidate["mae_kwh"]) / strongest["mae_kwh"] * 100, 9),
                "rmse_relative_improvement_percent": round((strongest["rmse_kwh"] - candidate["rmse_kwh"]) / strongest["rmse_kwh"] * 100, 9),
                "peak_overlap_percentage_point_difference": round(candidate["peak_overlap_percent"] - strongest["peak_overlap_percent"], 9),
                "period_total_mape_relative_improvement_percent": round((strongest["period_total_mape_percent"] - candidate["period_total_mape_percent"]) / strongest["period_total_mape_percent"] * 100, 9),
            }
        output[str(horizon)] = {
            "strongest_compatible_baseline_by_wape": strongest_name,
            "strongest_baseline_metrics": strongest,
            "candidate_comparisons": candidates,
        }
    return output


def _write_selected_final_models(rows: list[dict[str, str]]) -> dict[str, str]:
    cutoff = datetime.fromisoformat(rows[-1]["timestamp"])
    paths: dict[str, str] = {}
    for model_name in sorted(set(SELECTED_MODEL_BY_HORIZON.values())):
        model, training_observations = fit_candidate(rows, cutoff, model_name)
        path = MODEL_DIR / f"final_{model_name}.json"
        _save_model_artifact(path, model_name, model, cutoff, training_observations)
        paths[model_name] = str(path.relative_to(Path(__file__).resolve().parents[2]))
    return paths


def _write_figures(
    records_by_horizon_model: dict[int, dict[str, list[dict[str, Any]]]],
    metrics_by_horizon: dict[str, Any],
    comparison: dict[str, Any],
) -> list[str]:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for index, horizon in enumerate(HORIZONS, start=1):
        model_name = SELECTED_MODEL_BY_HORIZON[horizon]
        records = records_by_horizon_model[horizon][model_name]
        origins = sorted({record["forecast_origin"] for record in records})
        representative_origin = origins[len(origins) // 2]
        window = [record for record in records if record["forecast_origin"] == representative_origin]
        path = FIGURES_DIR / f"0{index}_actual_vs_forecast_{horizon}h.svg"
        line_chart(
            path,
            f"Representative {horizon}h forecast: {model_name}",
            [
                ("Actual", [record["actual_household_kwh"] for record in window]),
                ("Forecast", [record["predicted_household_kwh"] for record in window]),
            ],
            [datetime.fromisoformat(record["timestamp"]).strftime("%b %d %H:%M") for record in window],
            "kWh per hour",
        )
        created.append(path)

    labels = []
    values = []
    for horizon in HORIZONS:
        for model_name in MODEL_SPECS:
            labels.append(f"{horizon}h {model_name.replace('_GBT_', ' ').replace('_HISTORY', '').replace('_CAL_WEATHER', '')}")
            values.append(metrics_by_horizon[str(horizon)][model_name]["wape_percent"])
    path = FIGURES_DIR / "04_model_wape_by_horizon.svg"
    bar_chart(path, "Learned-model WAPE by forecast horizon", labels, values, "WAPE (%)")
    created.append(path)

    path = FIGURES_DIR / "05_selected_peak_overlap_by_horizon.svg"
    bar_chart(
        path,
        "Selected-model peak overlap by forecast horizon",
        [f"{horizon}h" for horizon in HORIZONS],
        [metrics_by_horizon[str(horizon)][SELECTED_MODEL_BY_HORIZON[horizon]]["peak_overlap_percent"] for horizon in HORIZONS],
        "Peak overlap (%)",
    )
    created.append(path)

    period_labels: list[str] = []
    period_actual: list[float] = []
    period_predicted: list[float] = []
    for horizon in HORIZONS:
        model_metrics = metrics_by_horizon[str(horizon)][SELECTED_MODEL_BY_HORIZON[horizon]]["per_origin"]
        for origin, item in model_metrics.items():
            period_labels.append(f"{horizon}h {origin[5:10]}")
            period_actual.append(item["actual_period_energy_kwh"])
            period_predicted.append(item["predicted_period_energy_kwh"])
    path = FIGURES_DIR / "06_period_total_actual_vs_predicted.svg"
    line_chart(path, "Selected forecasts: period-total actual versus predicted", [("Actual", period_actual), ("Predicted", period_predicted)], period_labels, "Period energy (kWh)")
    created.append(path)

    records168 = records_by_horizon_model[168][SELECTED_MODEL_BY_HORIZON[168]]
    lead_errors = []
    for lead in range(1, 169):
        errors = [abs(record["actual_household_kwh"] - record["predicted_household_kwh"]) for record in records168 if record["lead_hour"] == lead]
        lead_errors.append(statistics.mean(errors))
    path = FIGURES_DIR / "07_168h_error_by_lead_hour.svg"
    line_chart(path, "168h selected-model mean absolute error by lead hour", [("MAE", lead_errors)], [str(lead) for lead in range(1, 169)], "MAE (kWh)")
    created.append(path)

    compare_labels = []
    compare_values = []
    for horizon in HORIZONS:
        selected = SELECTED_MODEL_BY_HORIZON[horizon]
        baseline = comparison["by_horizon"][str(horizon)]["strongest_compatible_baseline_by_wape"]
        compare_labels.extend([f"{horizon}h selected", f"{horizon}h {baseline.split('_')[0]}"])
        compare_values.extend([
            metrics_by_horizon[str(horizon)][selected]["wape_percent"],
            metrics_by_horizon[str(horizon)][baseline]["wape_percent"],
        ])
    path = FIGURES_DIR / "08_selected_model_vs_baseline_wape.svg"
    bar_chart(path, "Selected model versus strongest compatible baseline", compare_labels, compare_values, "WAPE (%)")
    created.append(path)
    return [str(path.relative_to(Path(__file__).resolve().parents[2])) for path in created]


def main() -> int:
    if sha256(STAGE3C_INPUT) != FROZEN_STAGE3C_SHA256:
        raise RuntimeError("Frozen Stage 3C fingerprint does not match")
    rows = read_profile()
    row_by_timestamp = {row["timestamp"]: row for row in rows}
    schedules = origin_schedule(rows)
    unique_origins = sorted({origin for origins in schedules.values() for origin in origins})
    records_by_horizon_model: dict[int, dict[str, list[dict[str, Any]]]] = {
        horizon: {name: [] for name in (*MODEL_SPECS, *BASELINE_NAMES)} for horizon in HORIZONS
    }
    training_counts: dict[str, dict[str, int]] = {}

    for origin in unique_origins:
        applicable = [horizon for horizon, origins in schedules.items() if origin in origins]
        maximum_horizon = max(applicable)
        candidate_forecasts: dict[str, list[dict[str, Any]]] = {}
        training_counts[origin.isoformat()] = {}
        for model_name in MODEL_SPECS:
            model, training_observations = fit_candidate(rows, origin, model_name)
            training_counts[origin.isoformat()][model_name] = training_observations
            _save_model_artifact(
                _artifact_path(origin, model_name),
                model_name,
                model,
                origin,
                training_observations,
            )
            candidate_forecasts[model_name] = recursive_forecast(
                rows, origin, maximum_horizon, model_name, model
            )
        compatible_baselines = baseline_forecasts(rows, origin, maximum_horizon)
        for horizon in applicable:
            for model_name, forecast in {**candidate_forecasts, **compatible_baselines}.items():
                records_by_horizon_model[horizon][model_name].extend(
                    _enrich_record(record, horizon, row_by_timestamp)
                    for record in forecast[:horizon]
                )

    all_records = [
        record
        for horizon in HORIZONS
        for model_name in (*MODEL_SPECS, *BASELINE_NAMES)
        for record in records_by_horizon_model[horizon][model_name]
    ]
    PREDICTIONS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with PREDICTIONS_OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_records[0]))
        writer.writeheader()
        writer.writerows(all_records)

    metrics_by_horizon = {
        str(horizon): {
            model_name: aggregate_metrics(records)
            for model_name, records in records_by_horizon_model[horizon].items()
        }
        for horizon in HORIZONS
    }
    selected_final_artifacts = _write_selected_final_models(rows)
    metrics = {
        "stage": "5 - household electricity demand forecasting",
        "source_stage3c_sha256": sha256(STAGE3C_INPUT),
        "frozen_stage4_sha256": {
            "validation_metrics": sha256(STAGE4_METRICS),
            "baseline_metrics": sha256(STAGE4_BASELINES),
            "validation_report": sha256(STAGE4_REPORT),
        },
        "random_seed": RANDOM_SEED,
        "randomness_used": False,
        "split": "chronological rolling-origin; no random split",
        "origin_step_hours": 72,
        "origin_schedule": {
            str(horizon): [origin.isoformat() for origin in origins]
            for horizon, origins in schedules.items()
        },
        "perfect_weather_proxy_assumption": "Realized frozen Stage 2 weather at forecast timestamps is used as a proxy for future weather forecasts; scores exclude weather-forecast error.",
        "candidate_specifications": MODEL_SPECS,
        "feature_specifications": {
            "calendar_weather": feature_names("calendar_weather"),
            "calendar_weather_target_history": feature_names("calendar_weather_target_history"),
            "future_exogenous_features": WEATHER_FEATURES,
            "calendar_features": CALENDAR_FEATURES,
            "target_history_features": TARGET_HISTORY_FEATURES,
            "forbidden_future_predictors": FORBIDDEN_FUTURE_PREDICTORS,
        },
        "multi_step_strategy": "Recursive for target-history models: after each origin, unavailable future lag/trailing values use earlier predictions, never actual future household demand.",
        "non_negative_prediction_rule": "All model outputs are clipped with max(0, raw_prediction).",
        "training_observation_counts": training_counts,
        "metrics_by_horizon": metrics_by_horizon,
        "selection_status": "FINAL",
        "selected_model_by_horizon": {
            str(horizon): model_name for horizon, model_name in SELECTED_MODEL_BY_HORIZON.items()
        },
        "selection_reasons": SELECTION_REASONS,
        "selected_final_model_artifacts": selected_final_artifacts,
    }
    METRICS_OUTPUT.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    comparison = {
        "comparison_scope": "All model and baseline metrics use identical rolling-origin timestamps within each horizon.",
        "by_horizon": _comparison(metrics_by_horizon),
    }
    comparison["selected_model_by_horizon"] = {
        str(horizon): model_name for horizon, model_name in SELECTED_MODEL_BY_HORIZON.items()
    }
    comparison["selection_reasons"] = SELECTION_REASONS
    COMPARISON_OUTPUT.write_text(json.dumps(comparison, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    figures = _write_figures(records_by_horizon_model, metrics_by_horizon, comparison)

    contract = {
        "stage": "5 - frozen forecaster contract",
        "status": "FROZEN_STAGE5_FORECASTER",
        "required_forecast_columns": [
            "timestamp",
            "forecast_origin",
            "horizon_hours",
            "lead_hour",
            "predicted_household_kwh",
        ],
        "evaluation_only_columns": ["actual_household_kwh"],
        "selected_model_by_horizon": {
            str(horizon): model_name for horizon, model_name in SELECTED_MODEL_BY_HORIZON.items()
        },
        "selection_reasons": SELECTION_REASONS,
        "model_artifacts": selected_final_artifacts,
        "evaluation_model_artifact_pattern": "models/stage5/evaluation/{origin}_{model}.json",
        "forecasting_strategy": "One-step models with recursive multi-step prediction for target-history features; prior predictions replace unavailable post-origin targets.",
        "non_negative_clipping_rule": "predicted_household_kwh = max(0, raw_prediction)",
        "weather_input_assumption": "Evaluation uses realized Stage 2 weather as a perfect-weather proxy; operational forecasts require forecast weather for the same four fields.",
        "future_inputs": [*WEATHER_FEATURES, "forecast timestamp calendar variables"],
        "forbidden_future_inputs": list(FORBIDDEN_FUTURE_PREDICTORS),
        "target_history_requirement": "Observed household_total_kwh through forecast origin; recursive predictions thereafter.",
        "perfect_weather_proxy_evaluation_only": True,
        "production_ready": False,
        "stage6_started": False,
        "validation_figures": figures,
    }
    CONTRACT_OUTPUT.write_text(json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    (MODEL_DIR / "candidate_specifications.json").write_text(
        json.dumps(
            {
                "source_stage3c_sha256": sha256(STAGE3C_INPUT),
                "candidate_specifications": MODEL_SPECS,
                "feature_specifications": metrics["feature_specifications"],
                "random_seed": RANDOM_SEED,
                "hyperparameter_selection": "Fixed conservative defaults chosen before September evaluation; no search performed.",
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"origins": len(unique_origins), "prediction_rows": len(all_records), "selection_status": "FINAL", "selected_model_by_horizon": contract["selected_model_by_horizon"], "figures": len(figures)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
