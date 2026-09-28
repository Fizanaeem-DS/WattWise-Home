"""Leakage-safe feature construction, recursion, evaluation, and baselines."""

from __future__ import annotations

from collections import defaultdict
import csv
from datetime import datetime, timedelta
import hashlib
import math
from pathlib import Path
import statistics
from typing import Any

import numpy as np

from .config import (
    BASELINE_NAMES,
    CALENDAR_FEATURES,
    HORIZONS,
    MODEL_SPECS,
    ORIGIN_START,
    ORIGIN_STEP_HOURS,
    STAGE3C_INPUT,
    TARGET_HISTORY_FEATURES,
    WEATHER_FEATURES,
)
from .models import GradientBoostedRegressor, RidgeRegressor


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_profile(path: Path = STAGE3C_INPUT) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def feature_names(feature_set: str) -> tuple[str, ...]:
    base = (*CALENDAR_FEATURES, *WEATHER_FEATURES)
    return base if feature_set == "calendar_weather" else (*base, *TARGET_HISTORY_FEATURES)


def origin_schedule(rows: list[dict[str, str]]) -> dict[int, list[datetime]]:
    last = datetime.fromisoformat(rows[-1]["timestamp"])
    start = datetime.fromisoformat(ORIGIN_START)
    schedules: dict[int, list[datetime]] = {}
    for horizon in HORIZONS:
        origins = []
        current = start
        while current + timedelta(hours=horizon) <= last:
            origins.append(current)
            current += timedelta(hours=ORIGIN_STEP_HOURS)
        schedules[horizon] = origins
    return schedules


def _calendar_weather(row: dict[str, str], timestamp: datetime) -> list[float]:
    hour_angle = 2 * math.pi * timestamp.hour / 24
    weekday_angle = 2 * math.pi * timestamp.weekday() / 7
    year_days = 365
    day_angle = 2 * math.pi * (timestamp.timetuple().tm_yday - 1) / year_days
    return [
        math.sin(hour_angle),
        math.cos(hour_angle),
        math.sin(weekday_angle),
        math.cos(weekday_angle),
        float(timestamp.weekday() >= 5),
        math.sin(day_angle),
        math.cos(day_angle),
        *[float(row[column]) for column in WEATHER_FEATURES],
    ]


def _history_features(
    timestamp: datetime,
    values: dict[datetime, float],
    origin: datetime | None,
) -> tuple[list[float], dict[str, Any]]:
    lag_hours = (1, 2, 3, 24, 48, 168)
    references: list[datetime] = []
    features: list[float] = []
    for lag in lag_hours:
        reference = timestamp - timedelta(hours=lag)
        references.append(reference)
        features.append(values[reference])
    for window in (3, 6, 24):
        window_references = [timestamp - timedelta(hours=lag) for lag in range(1, window + 1)]
        references.extend(window_references)
        features.append(statistics.mean(values[reference] for reference in window_references))
    actual_references = references if origin is None else [reference for reference in references if reference <= origin]
    recursive_references = [] if origin is None else [reference for reference in references if reference > origin]
    audit = {
        "maximum_actual_target_reference": max(actual_references).isoformat() if actual_references else None,
        "recursive_prediction_reference_count": len(recursive_references),
        "actual_future_target_used": False if origin is not None else None,
    }
    return features, audit


def training_matrix(
    rows: list[dict[str, str]],
    cutoff: datetime,
    feature_set: str,
) -> tuple[np.ndarray, np.ndarray]:
    row_by_time = {datetime.fromisoformat(row["timestamp"]): row for row in rows}
    values = {timestamp: float(row["household_total_kwh"]) for timestamp, row in row_by_time.items()}
    ordered = sorted(timestamp for timestamp in row_by_time if timestamp <= cutoff)
    x_rows: list[list[float]] = []
    y: list[float] = []
    for timestamp in ordered:
        if (
            feature_set == "calendar_weather_target_history"
            and timestamp - timedelta(hours=168) not in values
        ):
            continue
        features = _calendar_weather(row_by_time[timestamp], timestamp)
        if feature_set == "calendar_weather_target_history":
            history, _ = _history_features(timestamp, values, None)
            features.extend(history)
        x_rows.append(features)
        y.append(values[timestamp])
    return np.array(x_rows, dtype=float), np.array(y, dtype=float)


def fit_candidate(rows: list[dict[str, str]], cutoff: datetime, name: str):
    spec = MODEL_SPECS[name]
    x, y = training_matrix(rows, cutoff, spec["feature_set"])
    parameters = spec["hyperparameters"]
    if spec["model_type"] == "gradient_boosted_regression_trees":
        model = GradientBoostedRegressor(**parameters)
    else:
        model = RidgeRegressor(**parameters)
    model.fit(x, y)
    return model, len(y)


def recursive_forecast(
    rows: list[dict[str, str]],
    origin: datetime,
    horizon: int,
    name: str,
    model,
) -> list[dict[str, Any]]:
    spec = MODEL_SPECS[name]
    row_by_time = {datetime.fromisoformat(row["timestamp"]): row for row in rows}
    history = {
        timestamp: float(row["household_total_kwh"])
        for timestamp, row in row_by_time.items()
        if timestamp <= origin
    }
    predictions: list[dict[str, Any]] = []
    for lead in range(1, horizon + 1):
        timestamp = origin + timedelta(hours=lead)
        row = row_by_time[timestamp]
        features = _calendar_weather(row, timestamp)
        audit = {
            "maximum_actual_target_reference": None,
            "recursive_prediction_reference_count": 0,
            "actual_future_target_used": False,
        }
        if spec["feature_set"] == "calendar_weather_target_history":
            target_features, audit = _history_features(timestamp, history, origin)
            features.extend(target_features)
        raw = float(model.predict(np.array([features], dtype=float))[0])
        prediction = max(0.0, raw)
        history[timestamp] = prediction
        predictions.append(
            {
                "timestamp": timestamp.isoformat(),
                "forecast_origin": origin.isoformat(),
                "lead_hour": lead,
                "model": name,
                "predicted_household_kwh": prediction,
                "actual_household_kwh": float(row["household_total_kwh"]),
                "prediction_clipped_to_zero": raw < 0,
                **audit,
            }
        )
    return predictions


def baseline_forecasts(
    rows: list[dict[str, str]], origin: datetime, horizon: int
) -> dict[str, list[dict[str, Any]]]:
    row_by_time = {datetime.fromisoformat(row["timestamp"]): row for row in rows}
    actual = {timestamp: float(row["household_total_kwh"]) for timestamp, row in row_by_time.items()}
    available = {timestamp: value for timestamp, value in actual.items() if timestamp <= origin}
    hour_of_week: dict[int, list[float]] = defaultdict(list)
    for timestamp, value in available.items():
        hour_of_week[timestamp.weekday() * 24 + timestamp.hour].append(value)
    lookup = {slot: statistics.mean(values) for slot, values in hour_of_week.items()}
    outputs = {name: [] for name in BASELINE_NAMES}
    b1_history = dict(available)
    for lead in range(1, horizon + 1):
        timestamp = origin + timedelta(hours=lead)
        truth = actual[timestamp]
        b1_source = timestamp - timedelta(hours=24)
        b2_source = timestamp - timedelta(hours=168)
        b1_prediction = b1_history[b1_source]
        b1_history[timestamp] = b1_prediction
        values = {
            "B1_PREVIOUS_DAY": (b1_prediction, b1_source.isoformat(), b1_source > origin),
            "B2_PREVIOUS_WEEK": (available[b2_source], b2_source.isoformat(), False),
            "B3_HOUR_OF_WEEK_MEAN": (lookup[timestamp.weekday() * 24 + timestamp.hour], None, False),
        }
        for name, (prediction, source_timestamp, recursive) in values.items():
            outputs[name].append(
                {
                    "timestamp": timestamp.isoformat(),
                    "forecast_origin": origin.isoformat(),
                    "lead_hour": lead,
                    "model": name,
                    "predicted_household_kwh": prediction,
                    "actual_household_kwh": truth,
                    "prediction_clipped_to_zero": False,
                    "maximum_actual_target_reference": (
                        source_timestamp if source_timestamp and not recursive else origin.isoformat()
                    ),
                    "recursive_prediction_reference_count": int(recursive),
                    "actual_future_target_used": False,
                }
            )
    return outputs


def _window_metrics(records: list[dict[str, Any]]) -> dict[str, float]:
    actual = [record["actual_household_kwh"] for record in records]
    predicted = [record["predicted_household_kwh"] for record in records]
    errors = [truth - estimate for truth, estimate in zip(actual, predicted)]
    absolute = [abs(error) for error in errors]
    peak_count = math.ceil(len(records) * 0.10)
    actual_peak = {
        record["timestamp"]
        for record in sorted(records, key=lambda item: (-item["actual_household_kwh"], item["timestamp"]))[:peak_count]
    }
    predicted_peak = {
        record["timestamp"]
        for record in sorted(records, key=lambda item: (-item["predicted_household_kwh"], item["timestamp"]))[:peak_count]
    }
    actual_energy = sum(actual)
    predicted_energy = sum(predicted)
    return {
        "mae_kwh": statistics.mean(absolute),
        "rmse_kwh": math.sqrt(statistics.mean(error * error for error in errors)),
        "wape_percent": sum(absolute) / sum(abs(value) for value in actual) * 100,
        "actual_period_energy_kwh": actual_energy,
        "predicted_period_energy_kwh": predicted_energy,
        "period_total_absolute_percentage_error": abs(predicted_energy - actual_energy) / actual_energy * 100,
        "period_total_signed_percentage_error": (predicted_energy - actual_energy) / actual_energy * 100,
        "peak_overlap_percent": len(actual_peak & predicted_peak) / peak_count * 100,
        "peak_magnitude_absolute_error_kwh": abs(max(actual) - max(predicted)),
    }


def aggregate_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_origin: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_origin[record["forecast_origin"]].append(record)
    window = {origin: _window_metrics(items) for origin, items in by_origin.items()}
    actual = [record["actual_household_kwh"] for record in records]
    predicted = [record["predicted_household_kwh"] for record in records]
    absolute = [abs(truth - estimate) for truth, estimate in zip(actual, predicted)]
    origin_wapes = [item["wape_percent"] for item in window.values()]
    return {
        "evaluated_forecast_origins": list(window),
        "forecast_origin_count": len(window),
        "evaluated_hourly_observations": len(records),
        "mae_kwh": round(statistics.mean(absolute), 9),
        "rmse_kwh": round(math.sqrt(statistics.mean((truth - estimate) ** 2 for truth, estimate in zip(actual, predicted))), 9),
        "wape_percent": round(sum(absolute) / sum(abs(value) for value in actual) * 100, 9),
        "period_total_mape_percent": round(statistics.mean(item["period_total_absolute_percentage_error"] for item in window.values()), 9),
        "period_total_mean_signed_bias_percent": round(statistics.mean(item["period_total_signed_percentage_error"] for item in window.values()), 9),
        "peak_overlap_percent": round(statistics.mean(item["peak_overlap_percent"] for item in window.values()), 9),
        "peak_magnitude_mae_kwh": round(statistics.mean(item["peak_magnitude_absolute_error_kwh"] for item in window.values()), 9),
        "origin_wape_stability": {
            "minimum_percent": round(min(origin_wapes), 9),
            "mean_percent": round(statistics.mean(origin_wapes), 9),
            "maximum_percent": round(max(origin_wapes), 9),
            "population_standard_deviation_percent": round(statistics.pstdev(origin_wapes), 9),
        },
        "per_origin": {
            origin: {key: round(value, 9) for key, value in item.items()}
            for origin, item in window.items()
        },
    }
