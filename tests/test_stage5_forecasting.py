"""Independent leakage, metric, artifact, and determinism tests for Stage 5."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hackowatt_stage5.config import (  # noqa: E402
    BASELINE_NAMES,
    FORBIDDEN_FUTURE_PREDICTORS,
    FROZEN_STAGE3C_SHA256,
    HORIZONS,
    MODEL_SPECS,
    STAGE3C_INPUT,
    STAGE4_BASELINES,
    STAGE4_METRICS,
    STAGE4_REPORT,
    WEATHER_FEATURES,
)
from hackowatt_stage5.forecasting import (  # noqa: E402
    fit_candidate,
    origin_schedule,
    read_profile,
    recursive_forecast,
)
from hackowatt_stage5.models import model_from_dict  # noqa: E402


PREDICTIONS = ROOT / "data" / "processed" / "stage5_forecast_predictions.csv"
METRICS = ROOT / "data" / "processed" / "stage5_model_metrics.json"
COMPARISON = ROOT / "data" / "processed" / "stage5_baseline_comparison.json"
CONTRACT = ROOT / "data" / "processed" / "stage5_forecast_contract.json"
MODEL_DIR = ROOT / "models" / "stage5"
FIGURES_DIR = ROOT / "artifacts" / "stage5_forecasting"
FROZEN_STAGE4_HASHES = {
    STAGE4_METRICS: "ab42b583a8de26731ba2bc80be04582f27d29a79cccb8600c5f1023422a02417",
    STAGE4_BASELINES: "b7d377b4b176f4b7d0ebefa09d7ab4d5dfb3f4e2fd8683ff4e9777d8d4e3fc12",
    STAGE4_REPORT: "cbeb57f269439960fb3b91f4ddB095f35e63e1e64ad7372635eadb08b4651878".lower(),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class Stage5ForecastingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = read_profile()
        cls.predictions = read_csv(PREDICTIONS)
        cls.metrics = json.loads(METRICS.read_text(encoding="utf-8"))
        cls.comparison = json.loads(COMPARISON.read_text(encoding="utf-8"))
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.schedules = origin_schedule(cls.profile)

    def test_frozen_stage3c_and_stage4_fingerprints_unchanged(self) -> None:
        self.assertEqual(sha256(STAGE3C_INPUT), FROZEN_STAGE3C_SHA256)
        self.assertEqual(self.metrics["source_stage3c_sha256"], FROZEN_STAGE3C_SHA256)
        for path, expected in FROZEN_STAGE4_HASHES.items():
            self.assertEqual(sha256(path), expected)

    def test_no_random_split_and_origin_schedule_is_reproducible(self) -> None:
        self.assertEqual(self.metrics["split"], "chronological rolling-origin; no random split")
        self.assertFalse(self.metrics["randomness_used"])
        expected_counts = {24: 10, 72: 9, 168: 8}
        for horizon, origins in self.schedules.items():
            self.assertEqual(len(origins), expected_counts[horizon])
            self.assertEqual(origins, sorted(origins))
            self.assertTrue(all(b - a == timedelta(hours=72) for a, b in zip(origins, origins[1:])))
            self.assertEqual(
                self.metrics["origin_schedule"][str(horizon)],
                [origin.isoformat() for origin in origins],
            )

    def test_every_target_is_strictly_after_its_origin(self) -> None:
        for row in self.predictions:
            timestamp = datetime.fromisoformat(row["timestamp"])
            origin = datetime.fromisoformat(row["forecast_origin"])
            self.assertGreater(timestamp, origin)
            self.assertEqual(timestamp - origin, timedelta(hours=int(row["lead_hour"])))

    def test_target_history_never_reads_actual_future_values(self) -> None:
        for row in self.predictions:
            self.assertEqual(row["actual_future_target_used"], "False")
            reference = row["maximum_actual_target_reference"]
            if reference:
                self.assertLessEqual(
                    datetime.fromisoformat(reference),
                    datetime.fromisoformat(row["forecast_origin"]),
                )
        recursive_m2 = [
            row for row in self.predictions
            if row["model"] == "M2_GBT_HISTORY" and int(row["lead_hour"]) > 1
        ]
        self.assertTrue(any(int(row["recursive_prediction_reference_count"]) > 0 for row in recursive_m2))

    def test_feature_sets_exclude_future_latent_twin_state(self) -> None:
        specifications = self.metrics["feature_specifications"]
        allowed = set(specifications["calendar_weather_target_history"])
        self.assertTrue(set(WEATHER_FEATURES) <= allowed)
        self.assertTrue(set(FORBIDDEN_FUTURE_PREDICTORS).isdisjoint(allowed))
        self.assertEqual(set(specifications["future_exogenous_features"]), set(WEATHER_FEATURES))
        self.assertTrue(self.contract["perfect_weather_proxy_evaluation_only"])

    def test_exact_prediction_count_per_origin_and_horizon(self) -> None:
        grouped: dict[tuple[str, int, str], list[dict[str, str]]] = defaultdict(list)
        for row in self.predictions:
            grouped[(row["forecast_origin"], int(row["horizon_hours"]), row["model"])].append(row)
        all_models = {*MODEL_SPECS, *BASELINE_NAMES}
        for horizon in HORIZONS:
            for origin in self.schedules[horizon]:
                for model in all_models:
                    records = grouped[(origin.isoformat(), horizon, model)]
                    self.assertEqual(len(records), horizon)
                    self.assertEqual(sorted(int(row["lead_hour"]) for row in records), list(range(1, horizon + 1)))

    def test_all_predictions_are_finite_and_nonnegative(self) -> None:
        values = [float(row["predicted_household_kwh"]) for row in self.predictions]
        self.assertTrue(all(math.isfinite(value) for value in values))
        self.assertTrue(all(value >= 0 for value in values))
        self.assertEqual(self.contract["non_negative_clipping_rule"], "predicted_household_kwh = max(0, raw_prediction)")

    def _records(self, horizon: int, model: str) -> list[dict[str, str]]:
        return [
            row for row in self.predictions
            if int(row["horizon_hours"]) == horizon and row["model"] == model
        ]

    def test_hourly_metrics_recompute(self) -> None:
        for horizon in HORIZONS:
            for model in (*MODEL_SPECS, *BASELINE_NAMES):
                records = self._records(horizon, model)
                actual = [float(row["actual_household_kwh"]) for row in records]
                predicted = [float(row["predicted_household_kwh"]) for row in records]
                absolute = [abs(a - p) for a, p in zip(actual, predicted)]
                saved = self.metrics["metrics_by_horizon"][str(horizon)][model]
                self.assertAlmostEqual(saved["mae_kwh"], statistics.mean(absolute), places=9)
                self.assertAlmostEqual(saved["rmse_kwh"], math.sqrt(statistics.mean((a - p) ** 2 for a, p in zip(actual, predicted))), places=9)
                self.assertAlmostEqual(saved["wape_percent"], sum(absolute) / sum(actual) * 100, places=9)

    def test_period_total_energy_metrics_recompute(self) -> None:
        for horizon in HORIZONS:
            for model in (*MODEL_SPECS, *BASELINE_NAMES):
                by_origin: dict[str, list[dict[str, str]]] = defaultdict(list)
                for row in self._records(horizon, model):
                    by_origin[row["forecast_origin"]].append(row)
                absolute_percent = []
                signed_percent = []
                for records in by_origin.values():
                    actual = sum(float(row["actual_household_kwh"]) for row in records)
                    predicted = sum(float(row["predicted_household_kwh"]) for row in records)
                    signed = (predicted - actual) / actual * 100
                    signed_percent.append(signed)
                    absolute_percent.append(abs(signed))
                saved = self.metrics["metrics_by_horizon"][str(horizon)][model]
                self.assertAlmostEqual(saved["period_total_mape_percent"], statistics.mean(absolute_percent), places=9)
                self.assertAlmostEqual(saved["period_total_mean_signed_bias_percent"], statistics.mean(signed_percent), places=9)

    def test_peak_overlap_and_magnitude_error_recompute(self) -> None:
        for horizon in HORIZONS:
            for model in (*MODEL_SPECS, *BASELINE_NAMES):
                by_origin: dict[str, list[dict[str, str]]] = defaultdict(list)
                for row in self._records(horizon, model):
                    by_origin[row["forecast_origin"]].append(row)
                overlaps = []
                magnitude_errors = []
                for records in by_origin.values():
                    count = math.ceil(len(records) * 0.10)
                    actual_peak = {
                        row["timestamp"] for row in sorted(records, key=lambda item: (-float(item["actual_household_kwh"]), item["timestamp"]))[:count]
                    }
                    predicted_peak = {
                        row["timestamp"] for row in sorted(records, key=lambda item: (-float(item["predicted_household_kwh"]), item["timestamp"]))[:count]
                    }
                    overlaps.append(len(actual_peak & predicted_peak) / count * 100)
                    magnitude_errors.append(abs(max(float(row["actual_household_kwh"]) for row in records) - max(float(row["predicted_household_kwh"]) for row in records)))
                saved = self.metrics["metrics_by_horizon"][str(horizon)][model]
                self.assertAlmostEqual(saved["peak_overlap_percent"], statistics.mean(overlaps), places=9)
                self.assertAlmostEqual(saved["peak_magnitude_mae_kwh"], statistics.mean(magnitude_errors), places=9)

    def test_compatible_baselines_use_identical_evaluation_timestamps(self) -> None:
        for horizon in HORIZONS:
            reference = {
                (row["forecast_origin"], row["timestamp"])
                for row in self._records(horizon, "M1_GBT_CAL_WEATHER")
            }
            for model in (*MODEL_SPECS, *BASELINE_NAMES):
                timestamps = {
                    (row["forecast_origin"], row["timestamp"])
                    for row in self._records(horizon, model)
                }
                self.assertEqual(timestamps, reference)

    def test_b3_uses_only_values_available_at_each_origin(self) -> None:
        actual = {
            datetime.fromisoformat(row["timestamp"]): float(row["household_total_kwh"])
            for row in self.profile
        }
        for horizon in HORIZONS:
            for row in self._records(horizon, "B3_HOUR_OF_WEEK_MEAN"):
                origin = datetime.fromisoformat(row["forecast_origin"])
                target = datetime.fromisoformat(row["timestamp"])
                slot_values = [
                    value for timestamp, value in actual.items()
                    if timestamp <= origin
                    and timestamp.weekday() == target.weekday()
                    and timestamp.hour == target.hour
                ]
                self.assertAlmostEqual(float(row["predicted_household_kwh"]), statistics.mean(slot_values), places=12)

    def test_serialized_evaluation_models_reproduce_saved_predictions(self) -> None:
        origin = self.schedules[24][0]
        for model_name in MODEL_SPECS:
            stamp = origin.strftime("%Y%m%dT%H%M%S%z")
            artifact = json.loads((MODEL_DIR / "evaluation" / f"{stamp}_{model_name}.json").read_text(encoding="utf-8"))
            model = model_from_dict(artifact["model"])
            reproduced = recursive_forecast(self.profile, origin, 24, model_name, model)
            saved = sorted(
                (
                    row for row in self._records(24, model_name)
                    if row["forecast_origin"] == origin.isoformat()
                ),
                key=lambda row: int(row["lead_hour"]),
            )
            for generated, row in zip(reproduced, saved):
                self.assertAlmostEqual(generated["predicted_household_kwh"], float(row["predicted_household_kwh"]), places=12)

    def test_fixed_model_training_is_deterministic(self) -> None:
        origin = self.schedules[24][0]
        first, first_count = fit_candidate(self.profile, origin, "M2_GBT_HISTORY")
        second, second_count = fit_candidate(self.profile, origin, "M2_GBT_HISTORY")
        self.assertEqual(first_count, second_count)
        self.assertEqual(first.to_dict(), second.to_dict())
        first_forecast = recursive_forecast(self.profile, origin, 24, "M2_GBT_HISTORY", first)
        second_forecast = recursive_forecast(self.profile, origin, 24, "M2_GBT_HISTORY", second)
        self.assertEqual(first_forecast, second_forecast)

    def test_contract_and_selected_artifacts_are_complete(self) -> None:
        self.assertEqual(
            self.contract["selected_model_by_horizon"],
            {"24": "M2_GBT_HISTORY", "72": "M1_GBT_CAL_WEATHER", "168": "M1_GBT_CAL_WEATHER"},
        )
        for relative in self.contract["model_artifacts"].values():
            self.assertTrue((ROOT / relative).is_file())
        self.assertFalse(self.contract["production_ready"])
        self.assertFalse(self.contract["stage6_started"])
        figures = list(FIGURES_DIR.glob("*.svg"))
        self.assertEqual(len(figures), 8)
        for path in figures:
            content = path.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("<svg"))
            self.assertTrue(content.rstrip().endswith("</svg>"))


if __name__ == "__main__":
    unittest.main()
