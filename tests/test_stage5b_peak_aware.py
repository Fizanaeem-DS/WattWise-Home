"""Independent boundary, metric, comparison, and determinism tests for Stage 5B."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hackowatt_stage5.config import FORBIDDEN_FUTURE_PREDICTORS, HORIZONS  # noqa: E402
from hackowatt_stage5.forecasting import origin_schedule, read_profile  # noqa: E402
from hackowatt_stage5b.config import (  # noqa: E402
    COMPARATORS_BY_HORIZON,
    COMPARISON_OUTPUT,
    DIAGNOSTICS_OUTPUT,
    FROZEN_STAGE3C_SHA256,
    FROZEN_STAGE4_SHA256,
    FROZEN_STAGE5_FULL_MANIFEST_SHA256,
    FROZEN_STAGE5_SHA256,
    METRICS_OUTPUT,
    PREDICTIONS_OUTPUT,
    PROJECT_ROOT,
    STAGE3C_INPUT,
    STAGE4_BASELINES,
    STAGE4_METRICS,
    STAGE4_REPORT,
    STAGE5_COMPARISON,
    STAGE5_CONTRACT,
    STAGE5_METRICS,
    STAGE5_PREDICTIONS,
)
from hackowatt_stage5b.pipeline import main, stage5_manifest  # noqa: E402


FIGURE = ROOT / "artifacts" / "stage5b" / "168h_problem_window_comparison.svg"
MODEL_DIR = ROOT / "models" / "stage5b" / "evaluation"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class Stage5BPeakAwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = read_profile()
        cls.predictions = read_csv(PREDICTIONS_OUTPUT)
        cls.frozen_predictions = read_csv(STAGE5_PREDICTIONS)
        cls.metrics = json.loads(METRICS_OUTPUT.read_text(encoding="utf-8"))
        cls.comparison = json.loads(COMPARISON_OUTPUT.read_text(encoding="utf-8"))
        cls.schedules = origin_schedule(cls.profile)

    def _records(self, horizon: int) -> list[dict[str, str]]:
        return [row for row in self.predictions if int(row["horizon_hours"]) == horizon]

    def test_01_stage3c_frozen_hash_unchanged(self) -> None:
        self.assertEqual(sha256(STAGE3C_INPUT), FROZEN_STAGE3C_SHA256)

    def test_02_stage4_frozen_artifacts_unchanged(self) -> None:
        observed = {
            "validation_metrics": sha256(STAGE4_METRICS),
            "baseline_metrics": sha256(STAGE4_BASELINES),
            "validation_report": sha256(STAGE4_REPORT),
        }
        self.assertEqual(observed, FROZEN_STAGE4_SHA256)

    def test_03_existing_stage5_artifacts_unchanged(self) -> None:
        observed = {
            "predictions": sha256(STAGE5_PREDICTIONS),
            "metrics": sha256(STAGE5_METRICS),
            "comparison": sha256(STAGE5_COMPARISON),
            "contract": sha256(STAGE5_CONTRACT),
        }
        self.assertEqual(observed, FROZEN_STAGE5_SHA256)
        self.assertEqual(stage5_manifest()[0], FROZEN_STAGE5_FULL_MANIFEST_SHA256)
        self.assertTrue(self.metrics["frozen_upstream_unchanged"])

    def test_04_same_rolling_origin_schedule_as_stage5(self) -> None:
        frozen_metrics = json.loads(STAGE5_METRICS.read_text(encoding="utf-8"))
        for horizon in HORIZONS:
            expected = [origin.isoformat() for origin in self.schedules[horizon]]
            self.assertEqual(self.metrics["origin_schedule"][str(horizon)], expected)
            self.assertEqual(frozen_metrics["origin_schedule"][str(horizon)], expected)

    def test_05_threshold_uses_only_history_through_origin(self) -> None:
        for origin_text, audit in self.metrics["training_by_origin"].items():
            origin = datetime.fromisoformat(origin_text)
            available = [
                float(row["household_total_kwh"])
                for row in self.profile
                if datetime.fromisoformat(row["timestamp"]) <= origin
            ]
            self.assertEqual(audit["threshold_history_observations"], len(available))
            self.assertAlmostEqual(
                audit["high_demand_threshold_kwh"],
                float(np.percentile(available, 90.0)),
                places=12,
            )

    def test_06_classifier_training_has_no_post_origin_target(self) -> None:
        for origin_text, audit in self.metrics["training_by_origin"].items():
            self.assertLessEqual(
                datetime.fromisoformat(audit["maximum_training_target_timestamp"]),
                datetime.fromisoformat(origin_text),
            )
            self.assertEqual(audit["post_origin_training_targets"], 0)

    def test_07_regression_training_has_no_post_origin_target_and_enough_high_rows(self) -> None:
        for origin_text, audit in self.metrics["training_by_origin"].items():
            self.assertLessEqual(
                datetime.fromisoformat(audit["maximum_training_target_timestamp"]),
                datetime.fromisoformat(origin_text),
            )
            self.assertGreaterEqual(audit["high_regime_training_observations"], 40)
            self.assertEqual(
                audit["normal_regime_training_observations"] + audit["high_regime_training_observations"],
                audit["training_observations"],
            )

    def test_08_no_forbidden_future_latent_state_is_used(self) -> None:
        features = set(self.metrics["method"]["feature_names"])
        self.assertTrue(features.isdisjoint(FORBIDDEN_FUTURE_PREDICTORS))
        self.assertEqual(
            set(self.metrics["method"]["forbidden_future_predictors"]),
            set(FORBIDDEN_FUTURE_PREDICTORS),
        )

    def test_09_recursive_history_never_reads_actual_post_origin_demand(self) -> None:
        recursive_rows = 0
        for row in self.predictions:
            self.assertEqual(row["actual_future_target_used"], "False")
            reference = row["maximum_actual_target_reference"]
            if reference:
                self.assertLessEqual(
                    datetime.fromisoformat(reference),
                    datetime.fromisoformat(row["forecast_origin"]),
                )
            recursive_rows += int(row["recursive_prediction_reference_count"]) > 0
        self.assertGreater(recursive_rows, 0)

    def test_10_predictions_are_finite_and_nonnegative(self) -> None:
        values = [float(row["predicted_household_kwh"]) for row in self.predictions]
        probabilities = [float(row["p_high_demand"]) for row in self.predictions]
        self.assertTrue(all(math.isfinite(value) and value >= 0.0 for value in values))
        self.assertTrue(all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in probabilities))

    def test_11_load_and_period_metrics_recompute_from_predictions(self) -> None:
        for horizon in HORIZONS:
            records = self._records(horizon)
            actual = [float(row["actual_household_kwh"]) for row in records]
            predicted = [float(row["predicted_household_kwh"]) for row in records]
            saved = self.metrics["metrics_by_horizon"][str(horizon)]["load_period_peak_metrics"]
            absolute = [abs(a - p) for a, p in zip(actual, predicted)]
            self.assertAlmostEqual(saved["mae_kwh"], statistics.mean(absolute), places=9)
            self.assertAlmostEqual(
                saved["rmse_kwh"],
                math.sqrt(statistics.mean((a - p) ** 2 for a, p in zip(actual, predicted))),
                places=9,
            )
            self.assertAlmostEqual(saved["wape_percent"], sum(absolute) / sum(actual) * 100, places=9)
            by_origin: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in records:
                by_origin[row["forecast_origin"]].append(row)
            signed = []
            for window in by_origin.values():
                actual_total = sum(float(row["actual_household_kwh"]) for row in window)
                predicted_total = sum(float(row["predicted_household_kwh"]) for row in window)
                signed.append((predicted_total - actual_total) / actual_total * 100)
            self.assertAlmostEqual(saved["period_total_mape_percent"], statistics.mean(abs(value) for value in signed), places=9)
            self.assertAlmostEqual(saved["period_total_mean_signed_bias_percent"], statistics.mean(signed), places=9)

    def test_12_high_demand_precision_recall_f1_recompute(self) -> None:
        for horizon in HORIZONS:
            records = self._records(horizon)
            actual_high = [float(row["actual_household_kwh"]) >= float(row["high_demand_threshold_kwh"]) for row in records]
            predicted_high = [float(row["predicted_household_kwh"]) >= float(row["high_demand_threshold_kwh"]) for row in records]
            true_positive = sum(actual and predicted for actual, predicted in zip(actual_high, predicted_high))
            precision = true_positive / sum(predicted_high) if any(predicted_high) else 0.0
            recall = true_positive / sum(actual_high) if any(actual_high) else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            saved = self.metrics["metrics_by_horizon"][str(horizon)]["high_demand_metrics"]
            self.assertAlmostEqual(saved["precision"], precision, places=9)
            self.assertAlmostEqual(saved["recall"], recall, places=9)
            self.assertAlmostEqual(saved["f1"], f1, places=9)
            self.assertEqual(saved["actual_high_demand_hours_captured"], true_positive)

    def test_13_stage5_and_stage5b_comparisons_use_identical_timestamps(self) -> None:
        for horizon in HORIZONS:
            candidate = {(row["forecast_origin"], row["timestamp"]) for row in self._records(horizon)}
            for model in COMPARATORS_BY_HORIZON[horizon]:
                frozen = {
                    (row["forecast_origin"], row["timestamp"])
                    for row in self.frozen_predictions
                    if int(row["horizon_hours"]) == horizon and row["model"] == model
                }
                self.assertEqual(candidate, frozen)
            self.assertTrue(self.comparison["by_horizon"][str(horizon)]["timestamp_identity_confirmed"])

    def test_14_deterministic_rerun_produces_identical_outputs(self) -> None:
        tracked = [PREDICTIONS_OUTPUT, METRICS_OUTPUT, COMPARISON_OUTPUT, DIAGNOSTICS_OUTPUT, FIGURE, *sorted(MODEL_DIR.glob("*.json"))]
        before = {path: sha256(path) for path in tracked}
        self.assertEqual(main(), 0)
        after = {path: sha256(path) for path in tracked}
        self.assertEqual(after, before)

    def test_15_peak_diagnostics_and_problem_figure_are_complete(self) -> None:
        diagnostics = read_csv(DIAGNOSTICS_OUTPUT)
        self.assertEqual(len(diagnostics), 30)
        self.assertEqual({int(row["horizon_hours"]) for row in diagnostics}, set(HORIZONS))
        for horizon in HORIZONS:
            self.assertEqual(sum(int(row["horizon_hours"]) == horizon for row in diagnostics), 10)
        self.assertTrue(FIGURE.read_text(encoding="utf-8").startswith("<svg"))
        self.assertEqual(self.metrics["acceptance_classification"], "NO USEFUL IMPROVEMENT")
        self.assertFalse(self.comparison["stage5_replaced"])


if __name__ == "__main__":
    unittest.main()

