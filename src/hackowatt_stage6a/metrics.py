"""Dependency-free Stage 6A discrimination, ranking, calibration, and interval metrics."""

from __future__ import annotations

from collections import defaultdict
import math
import statistics
from typing import Any


def roc_auc(labels: list[bool], scores: list[float]) -> float | None:
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return None
    ordered = sorted(zip(scores, labels), key=lambda item: item[0])
    rank_sum = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        average_rank = ((index + 1) + end) / 2.0
        rank_sum += average_rank * sum(label for _, label in ordered[index:end])
        index = end
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def average_precision(labels: list[bool], scores: list[float]) -> float | None:
    positives = sum(labels)
    if positives == 0:
        return None
    grouped: dict[float, list[bool]] = defaultdict(list)
    for label, score in zip(labels, scores):
        grouped[score].append(label)
    true_positive = 0
    seen = 0
    previous_recall = 0.0
    area = 0.0
    for score in sorted(grouped, reverse=True):
        group = grouped[score]
        true_positive += sum(group)
        seen += len(group)
        recall = true_positive / positives
        precision = true_positive / seen
        area += (recall - previous_recall) * precision
        previous_recall = recall
    return area


def discrimination(records: list[dict[str, Any]]) -> dict[str, Any]:
    labels = [bool(record["actual_high_demand"]) for record in records]
    scores = [float(record["peak_probability"]) for record in records]
    peak_scores = [score for score, label in zip(scores, labels) if label]
    non_peak_scores = [score for score, label in zip(scores, labels) if not label]
    return {
        "observation_count": len(records),
        "actual_high_demand_count": sum(labels),
        "actual_high_demand_prevalence": round(sum(labels) / len(labels), 9),
        "roc_auc": round(roc_auc(labels, scores), 9) if roc_auc(labels, scores) is not None else None,
        "pr_auc_average_precision": round(average_precision(labels, scores), 9) if average_precision(labels, scores) is not None else None,
        "mean_peak_probability_actual_peak": round(statistics.mean(peak_scores), 9) if peak_scores else None,
        "mean_peak_probability_actual_non_peak": round(statistics.mean(non_peak_scores), 9) if non_peak_scores else None,
    }


def mark_top_risk(records: list[dict[str, Any]]) -> None:
    count = math.ceil(len(records) * 0.10)
    ranked = sorted(records, key=lambda record: (-record["peak_probability"], record["timestamp"]))
    selected = {record["timestamp"] for record in ranked[:count]}
    baseline_ranked = sorted(
        records,
        key=lambda record: (-record["hour_of_day_baseline_risk"], record["timestamp"]),
    )
    baseline_selected = {record["timestamp"] for record in baseline_ranked[:count]}
    for record in records:
        record["top_10_percent_peak_risk"] = record["timestamp"] in selected
        record["top_10_percent_hour_baseline_risk"] = record["timestamp"] in baseline_selected


def top_risk_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_origin: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_origin[record["forecast_origin"]].append(record)
    windows: dict[str, Any] = {}
    for origin, window in sorted(by_origin.items()):
        actual_high = {record["timestamp"] for record in window if record["actual_high_demand"]}
        count = math.ceil(len(window) * 0.10)
        actual_top = {
            record["timestamp"]
            for record in sorted(window, key=lambda record: (-record["actual_household_kwh"], record["timestamp"]))[:count]
        }
        ensemble_top = {record["timestamp"] for record in window if record["top_10_percent_peak_risk"]}
        baseline_top = {record["timestamp"] for record in window if record["top_10_percent_hour_baseline_risk"]}
        windows[origin] = {
            "top_risk_timestamp_count": count,
            "actual_high_demand_count": len(actual_high),
            "ensemble_actual_high_capture_percent": round(len(ensemble_top & actual_high) / len(actual_high) * 100, 9) if actual_high else None,
            "hour_baseline_actual_high_capture_percent": round(len(baseline_top & actual_high) / len(actual_high) * 100, 9) if actual_high else None,
            "ensemble_actual_top10_overlap_percent": round(len(ensemble_top & actual_top) / count * 100, 9),
            "hour_baseline_actual_top10_overlap_percent": round(len(baseline_top & actual_top) / count * 100, 9),
        }
    keys = (
        "ensemble_actual_high_capture_percent",
        "hour_baseline_actual_high_capture_percent",
        "ensemble_actual_top10_overlap_percent",
        "hour_baseline_actual_top10_overlap_percent",
    )
    return {
        "per_origin": windows,
        "mean_across_origins": {
            key: round(statistics.mean(item[key] for item in windows.values() if item[key] is not None), 9)
            for key in keys
        },
        "chance_reference_percent": 10.0,
    }


def interval_metrics(records: list[dict[str, Any]]) -> dict[str, float]:
    p10_p90 = [record["ensemble_p10_kwh"] <= record["actual_household_kwh"] <= record["ensemble_p90_kwh"] for record in records]
    p05_p95 = [record["ensemble_p05_kwh"] <= record["actual_household_kwh"] <= record["ensemble_p95_kwh"] for record in records]
    return {
        "p10_p90_coverage_percent": round(statistics.mean(p10_p90) * 100, 9),
        "p10_p90_average_width_kwh": round(statistics.mean(record["ensemble_p90_kwh"] - record["ensemble_p10_kwh"] for record in records), 9),
        "p05_p95_coverage_percent": round(statistics.mean(p05_p95) * 100, 9),
        "p05_p95_average_width_kwh": round(statistics.mean(record["ensemble_p95_kwh"] - record["ensemble_p05_kwh"] for record in records), 9),
    }


def concentration(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record[key])].append(record)
    return {
        group: {
            "observation_count": len(items),
            "mean_peak_probability": round(statistics.mean(item["peak_probability"] for item in items), 9),
            "actual_high_demand_frequency": round(statistics.mean(bool(item["actual_high_demand"]) for item in items), 9),
        }
        for group, items in sorted(grouped.items())
    }


def calibration_rows(records_by_horizon: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for horizon, records in records_by_horizon.items():
        bins: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            bins[min(int(record["peak_probability"] * 10), 9)].append(record)
        for index in range(10):
            items = bins[index]
            output.append(
                {
                    "horizon_hours": horizon,
                    "probability_bin": f"{index / 10:.1f}-{(index + 1) / 10:.1f}",
                    "lower_bound_inclusive": index / 10,
                    "upper_bound_inclusive_only_for_last_bin": (index + 1) / 10,
                    "observation_count": len(items),
                    "mean_predicted_peak_probability": round(statistics.mean(item["peak_probability"] for item in items), 9) if items else "",
                    "actual_peak_frequency": round(statistics.mean(bool(item["actual_high_demand"]) for item in items), 9) if items else "",
                    "sample_size_at_least_30": len(items) >= 30,
                }
            )
    return output

