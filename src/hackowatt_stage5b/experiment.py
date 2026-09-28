"""Leakage-safe Stage 5B training, recursive forecasting, and evaluation helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
import math
import statistics
from typing import Any

import numpy as np

from hackowatt_stage5.forecasting import (
    _calendar_weather,
    _history_features,
    aggregate_metrics,
    feature_names,
)
from hackowatt_stage5.models import GradientBoostedRegressor

from .config import (
    CLASSIFIER_PARAMETERS,
    HIGH_DEMAND_PERCENTILE,
    MINIMUM_HIGH_REGIME_TRAINING_SAMPLES,
    REGRESSOR_PARAMETERS,
)
from .models import LogisticClassifier


def training_data(
    rows: list[dict[str, str]], origin: datetime
) -> tuple[np.ndarray, np.ndarray, list[datetime], float, int]:
    """Return M2-equivalent training features and an origin-only percentile threshold."""
    row_by_time = {datetime.fromisoformat(row["timestamp"]): row for row in rows}
    values = {timestamp: float(row["household_total_kwh"]) for timestamp, row in row_by_time.items()}
    history_times = sorted(timestamp for timestamp in row_by_time if timestamp <= origin)
    threshold = float(np.percentile([values[timestamp] for timestamp in history_times], HIGH_DEMAND_PERCENTILE))
    x_rows: list[list[float]] = []
    y_rows: list[float] = []
    timestamps: list[datetime] = []
    for timestamp in history_times:
        if timestamp - timedelta(hours=168) not in values:
            continue
        features = _calendar_weather(row_by_time[timestamp], timestamp)
        history, _ = _history_features(timestamp, values, None)
        features.extend(history)
        x_rows.append(features)
        y_rows.append(values[timestamp])
        timestamps.append(timestamp)
    labels = np.asarray(y_rows, dtype=float) >= threshold
    return (
        np.asarray(x_rows, dtype=float),
        np.asarray(y_rows, dtype=float),
        timestamps,
        threshold,
        int(np.sum(labels)),
    )


def fit_peak_aware(rows: list[dict[str, str]], origin: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
    x, y, timestamps, threshold, high_count = training_data(rows, origin)
    normal_count = len(y) - high_count
    if high_count < MINIMUM_HIGH_REGIME_TRAINING_SAMPLES:
        raise RuntimeError(
            f"High-demand regime has only {high_count} training observations at {origin.isoformat()}; "
            f"minimum is {MINIMUM_HIGH_REGIME_TRAINING_SAMPLES}."
        )
    high = y >= threshold
    classifier = LogisticClassifier(
        alpha=float(CLASSIFIER_PARAMETERS["alpha"]),
        max_iterations=int(CLASSIFIER_PARAMETERS["max_iterations"]),
        tolerance=float(CLASSIFIER_PARAMETERS["tolerance"]),
    ).fit(x, high.astype(float))
    normal_regressor = GradientBoostedRegressor(**REGRESSOR_PARAMETERS["normal"]).fit(x[~high], y[~high])
    high_regressor = GradientBoostedRegressor(**REGRESSOR_PARAMETERS["high"]).fit(x[high], y[high])
    models = {
        "classifier": classifier,
        "normal_regressor": normal_regressor,
        "high_regressor": high_regressor,
    }
    audit = {
        "origin": origin.isoformat(),
        "threshold_percentile": HIGH_DEMAND_PERCENTILE,
        "high_demand_threshold_kwh": threshold,
        "threshold_history_observations": sum(
            datetime.fromisoformat(row["timestamp"]) <= origin for row in rows
        ),
        "training_observations": len(y),
        "normal_regime_training_observations": normal_count,
        "high_regime_training_observations": high_count,
        "minimum_training_target_timestamp": timestamps[0].isoformat(),
        "maximum_training_target_timestamp": timestamps[-1].isoformat(),
        "post_origin_training_targets": 0,
    }
    return models, audit


def recursive_peak_aware_forecast(
    rows: list[dict[str, str]],
    origin: datetime,
    horizon: int,
    models: dict[str, Any],
    threshold: float,
) -> list[dict[str, Any]]:
    row_by_time = {datetime.fromisoformat(row["timestamp"]): row for row in rows}
    history = {
        timestamp: float(row["household_total_kwh"])
        for timestamp, row in row_by_time.items()
        if timestamp <= origin
    }
    output: list[dict[str, Any]] = []
    for lead in range(1, horizon + 1):
        timestamp = origin + timedelta(hours=lead)
        source = row_by_time[timestamp]
        features = _calendar_weather(source, timestamp)
        target_history, history_audit = _history_features(timestamp, history, origin)
        features.extend(target_history)
        matrix = np.asarray([features], dtype=float)
        probability = float(models["classifier"].predict_proba(matrix)[0])
        normal_prediction = float(models["normal_regressor"].predict(matrix)[0])
        high_prediction = float(models["high_regressor"].predict(matrix)[0])
        raw_prediction = (1.0 - probability) * normal_prediction + probability * high_prediction
        prediction = max(0.0, raw_prediction)
        actual = float(source["household_total_kwh"])
        history[timestamp] = prediction
        output.append(
            {
                "timestamp": timestamp.isoformat(),
                "forecast_origin": origin.isoformat(),
                "lead_hour": lead,
                "predicted_household_kwh": prediction,
                "actual_household_kwh": actual,
                "high_demand_threshold_kwh": threshold,
                "p_high_demand": probability,
                "normal_regime_prediction_kwh": normal_prediction,
                "high_regime_prediction_kwh": high_prediction,
                "actual_high_demand": actual >= threshold,
                "predicted_high_demand": prediction >= threshold,
                "classifier_probability_at_least_0_5": probability >= 0.5,
                "prediction_clipped_to_zero": raw_prediction < 0.0,
                **history_audit,
            }
        )
    return output


def high_demand_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    actual_high = [record for record in records if record["actual_household_kwh"] >= record["high_demand_threshold_kwh"]]
    predicted_high = [record for record in records if record["predicted_household_kwh"] >= record["high_demand_threshold_kwh"]]
    true_positive = sum(
        record["actual_household_kwh"] >= record["high_demand_threshold_kwh"]
        and record["predicted_household_kwh"] >= record["high_demand_threshold_kwh"]
        for record in records
    )
    precision = true_positive / len(predicted_high) if predicted_high else 0.0
    recall = true_positive / len(actual_high) if actual_high else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "classification_rule": "Actual and predicted demand are high when each is >= that forecast origin's training-history 90th-percentile threshold.",
        "precision": round(precision, 9),
        "recall": round(recall, 9),
        "f1": round(f1, 9),
        "actual_high_demand_hours": len(actual_high),
        "actual_high_demand_hours_captured": true_positive,
        "predicted_high_demand_hours": len(predicted_high),
        "mean_predicted_demand_during_actual_high_hours_kwh": round(
            statistics.mean(record["predicted_household_kwh"] for record in actual_high), 9
        ) if actual_high else None,
        "mean_actual_demand_during_actual_high_hours_kwh": round(
            statistics.mean(record["actual_household_kwh"] for record in actual_high), 9
        ) if actual_high else None,
    }


def evaluation_bundle(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "load_period_peak_metrics": aggregate_metrics(records),
        "high_demand_metrics": high_demand_metrics(records),
    }


def per_origin_thresholds(records: list[dict[str, Any]]) -> dict[str, float]:
    thresholds: dict[str, set[float]] = defaultdict(set)
    for record in records:
        thresholds[record["forecast_origin"]].add(record["high_demand_threshold_kwh"])
    if any(len(values) != 1 for values in thresholds.values()):
        raise AssertionError("Each origin must have exactly one high-demand threshold")
    return {origin: next(iter(values)) for origin, values in thresholds.items()}


def peak_diagnostic_rows(
    stage5b_by_horizon: dict[int, list[dict[str, Any]]],
    frozen_lookup: dict[tuple[int, str, str, str], dict[str, Any]],
    selected_by_horizon: dict[int, str],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for horizon, records in stage5b_by_horizon.items():
        largest = sorted(
            records,
            key=lambda record: (
                -record["actual_household_kwh"],
                record["forecast_origin"],
                record["timestamp"],
            ),
        )[:10]
        for rank, record in enumerate(largest, start=1):
            model_name = selected_by_horizon[horizon]
            frozen = frozen_lookup[(horizon, record["forecast_origin"], record["timestamp"], model_name)]
            before = abs(record["actual_household_kwh"] - frozen["predicted_household_kwh"])
            after = abs(record["actual_household_kwh"] - record["predicted_household_kwh"])
            output.append(
                {
                    "horizon_hours": horizon,
                    "actual_demand_rank": rank,
                    "forecast_origin": record["forecast_origin"],
                    "timestamp": record["timestamp"],
                    "actual_kwh": record["actual_household_kwh"],
                    "frozen_selected_model": model_name,
                    "frozen_selected_prediction_kwh": frozen["predicted_household_kwh"],
                    "stage5b_prediction_kwh": record["predicted_household_kwh"],
                    "absolute_error_before_kwh": before,
                    "absolute_error_after_kwh": after,
                    "absolute_error_change_kwh": after - before,
                    "p_high_demand": record["p_high_demand"],
                    "high_demand_threshold_kwh": record["high_demand_threshold_kwh"],
                }
            )
    return output

