"""Independent acceptance tests for the Stage 4 read-only validation gate."""

from __future__ import annotations

import csv
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

from hackowatt_stage4.analysis import (  # noqa: E402
    block_for_hour,
    compute_baseline_metrics,
    percentile,
)
from hackowatt_stage4.config import (  # noqa: E402
    CATEGORY_COLUMNS,
    FIGURES_DIR,
    STAGE3C_INPUT,
)


METRICS = ROOT / "data" / "processed" / "stage4_validation_metrics.json"
BASELINES = ROOT / "data" / "processed" / "stage4_baseline_metrics.json"
REPORT = ROOT / "data" / "processed" / "stage4_validation_report.json"
FROZEN_STAGE3C_SHA256 = "fde362de6c8d758af02efe02110741e8c1bc352b6ed3030441038804a2a8c54a"


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Stage4ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = read_csv(STAGE3C_INPUT)
        cls.metrics = json.loads(METRICS.read_text(encoding="utf-8"))
        cls.baselines = json.loads(BASELINES.read_text(encoding="utf-8"))
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.recomputed_baselines, cls.records = compute_baseline_metrics()

    def test_frozen_stage3c_fingerprint_is_unchanged_and_recorded(self) -> None:
        actual = sha256(STAGE3C_INPUT)
        self.assertEqual(actual, FROZEN_STAGE3C_SHA256)
        self.assertEqual(self.metrics["source"]["sha256"], actual)
        self.assertEqual(self.baselines["source_sha256"], actual)
        self.assertEqual(self.report["source_stage3c_sha256"], actual)
        self.assertTrue(self.metrics["source"]["read_only"])
        self.assertFalse(self.report["stage3_modified"])

    def test_exact_input_shape_and_timeline(self) -> None:
        self.assertEqual(len(self.rows), 1_464)
        timestamps = [datetime.fromisoformat(row["timestamp"]) for row in self.rows]
        self.assertEqual(len(set(timestamps)), 1_464)
        self.assertEqual(timestamps[0].isoformat(), "2025-08-01T00:00:00+02:00")
        self.assertEqual(timestamps[-1].isoformat(), "2025-09-30T23:00:00+02:00")
        self.assertTrue(all(b - a == timedelta(hours=1) for a, b in zip(timestamps, timestamps[1:])))
        self.assertEqual(len({timestamp.date() for timestamp in timestamps}), 61)

    def test_chronological_train_evaluation_split(self) -> None:
        split = self.baselines["split"]
        self.assertTrue(split["chronological"])
        self.assertFalse(split["random_split"])
        self.assertEqual(split["train_start"], "2025-08-01T00:00:00+02:00")
        self.assertEqual(split["train_end"], "2025-08-31T23:00:00+02:00")
        self.assertEqual(split["train_observations"], 744)
        self.assertEqual(split["evaluation_start"], "2025-09-01T00:00:00+02:00")
        self.assertEqual(split["evaluation_end"], "2025-09-30T23:00:00+02:00")
        self.assertEqual(split["evaluation_observations"], 720)

    def test_b1_uses_exactly_previous_24_hours(self) -> None:
        actual_by_time = {
            datetime.fromisoformat(row["timestamp"]): float(row["household_total_kwh"])
            for row in self.rows
        }
        for record in self.records["B1"]:
            timestamp = datetime.fromisoformat(record["timestamp"])
            source = datetime.fromisoformat(record["source_timestamp"])
            self.assertEqual(timestamp - source, timedelta(hours=24))
            self.assertEqual(record["prediction"], actual_by_time[source])

    def test_b2_uses_exactly_previous_168_hours(self) -> None:
        actual_by_time = {
            datetime.fromisoformat(row["timestamp"]): float(row["household_total_kwh"])
            for row in self.rows
        }
        for record in self.records["B2"]:
            timestamp = datetime.fromisoformat(record["timestamp"])
            source = datetime.fromisoformat(record["source_timestamp"])
            self.assertEqual(timestamp - source, timedelta(hours=168))
            self.assertEqual(record["prediction"], actual_by_time[source])

    def test_b3_lookup_uses_august_only_without_september_leakage(self) -> None:
        august: dict[int, list[float]] = {}
        for row in self.rows:
            timestamp = datetime.fromisoformat(row["timestamp"])
            if timestamp.month == 8:
                slot = timestamp.weekday() * 24 + timestamp.hour
                august.setdefault(slot, []).append(float(row["household_total_kwh"]))
        expected = {slot: statistics.mean(values) for slot, values in august.items()}
        for record in self.records["B3"]:
            timestamp = datetime.fromisoformat(record["timestamp"])
            self.assertEqual(timestamp.month, 9)
            self.assertEqual(record["prediction"], expected[record["hour_of_week_slot"]])
        self.assertEqual(self.baselines["b3_training"]["source_months"], ["2025-08"])
        self.assertFalse(self.baselines["b3_training"]["september_values_used"])
        self.assertEqual(self.baselines["b3_training"]["hour_of_week_slot_count"], 168)

    def test_baseline_error_metrics_recompute(self) -> None:
        for name, records in self.records.items():
            errors = [item["actual"] - item["prediction"] for item in records]
            absolute = [abs(error) for error in errors]
            expected_mae = statistics.mean(absolute)
            expected_rmse = math.sqrt(statistics.mean(error * error for error in errors))
            expected_wape = sum(absolute) / sum(abs(item["actual"]) for item in records) * 100
            saved = self.baselines["baselines"][name]
            self.assertAlmostEqual(saved["mae_kwh"], expected_mae, places=9)
            self.assertAlmostEqual(saved["rmse_kwh"], expected_rmse, places=9)
            self.assertAlmostEqual(saved["wape_percent"], expected_wape, places=9)

    def test_baseline_peak_overlap_recomputes(self) -> None:
        for name, records in self.records.items():
            peak_count = math.ceil(len(records) * 0.10)
            actual = {
                item["timestamp"]
                for item in sorted(records, key=lambda item: (-item["actual"], item["timestamp"]))[:peak_count]
            }
            predicted = {
                item["timestamp"]
                for item in sorted(records, key=lambda item: (-item["prediction"], item["timestamp"]))[:peak_count]
            }
            saved = self.baselines["baselines"][name]
            self.assertEqual(saved["actual_peak_count"], peak_count)
            self.assertEqual(saved["peak_overlap_count"], len(actual & predicted))
            self.assertAlmostEqual(saved["peak_overlap_percent"], len(actual & predicted) / peak_count * 100, places=9)

    def test_top_five_percent_peak_count_and_threshold(self) -> None:
        count = math.ceil(len(self.rows) * 0.05)
        values = sorted((float(row["household_total_kwh"]) for row in self.rows), reverse=True)
        saved = self.metrics["peak_face_validity"]["top_5_percent"]
        self.assertEqual(saved["count"], count)
        self.assertAlmostEqual(saved["threshold_kwh"], values[count - 1], places=9)
        self.assertEqual(sum(saved["hour_of_day_distribution"].values()), count)
        self.assertEqual(sum(saved["analysis_block_distribution"].values()), count)

    def test_analysis_block_assignment_is_complete_and_exact(self) -> None:
        expected = {
            **{hour: "NIGHT" for hour in (23, 0, 1, 2, 3, 4, 5, 6)},
            **{hour: "MORNING" for hour in (7, 8)},
            **{hour: "DAYTIME" for hour in range(9, 16)},
            **{hour: "RETURN_RAMP" for hour in range(16, 19)},
            **{hour: "EVENING" for hour in range(19, 23)},
        }
        self.assertEqual({hour: block_for_hour(hour) for hour in range(24)}, expected)
        counts = self.metrics["behavioral_face_validity"]["blocks"]
        self.assertEqual(sum(item["observation_count"] for item in counts.values()), 1_464)

    def test_component_and_category_reconciliation(self) -> None:
        for row in self.rows:
            category_total = sum(float(row[column]) for column in CATEGORY_COLUMNS)
            self.assertAlmostEqual(float(row["household_total_kwh"]), category_total, places=8)
        shares = self.metrics["energy_mix"]["category_percentage_shares"]
        self.assertAlmostEqual(sum(shares.values()), 100.0, places=7)

    def test_physical_rules_and_output_metrics_pass(self) -> None:
        self.assertTrue(self.metrics["input_integrity"]["all_checks_pass"])
        self.assertTrue(all(self.metrics["input_integrity"]["checks"].values()))
        self.assertTrue(self.metrics["physical_plausibility"]["all_checks_pass"])
        self.assertTrue(all(self.metrics["physical_plausibility"]["checks"].values()))
        total = sum(float(row["household_total_kwh"]) for row in self.rows)
        self.assertAlmostEqual(self.metrics["physical_plausibility"]["total_energy_kwh"], total, places=8)
        values = [float(row["household_total_kwh"]) for row in self.rows]
        self.assertAlmostEqual(self.metrics["physical_plausibility"]["hourly_energy_kwh"]["p95"], percentile(values, 0.95), places=9)

    def test_variability_and_classification_outputs(self) -> None:
        variability = self.metrics["day_to_day_variability"]
        self.assertEqual(variability["unique_24_hour_profiles"], 61)
        self.assertEqual(variability["pairwise_identical_day_count"], 0)
        self.assertEqual(self.report["classification"], "PASS")
        self.assertFalse(self.report["stage5_started"])

    def test_all_ten_svg_figures_exist_and_are_valid_svg(self) -> None:
        figures = sorted(FIGURES_DIR.glob("*.svg"))
        self.assertEqual(len(figures), 10)
        self.assertEqual(len(self.metrics["validation_figures"]), 10)
        for path in figures:
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("<svg"))
            self.assertTrue(text.rstrip().endswith("</svg>"))
            self.assertTrue("kWh" in text or "observation count" in text)


if __name__ == "__main__":
    unittest.main()
