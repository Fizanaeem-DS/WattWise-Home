"""Independent frozen-boundary, ensemble, metric, policy, and determinism tests for Stage 6A."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hackowatt_stage5.forecasting import origin_schedule, read_profile  # noqa: E402
from hackowatt_stage6a.config import (  # noqa: E402
    CALIBRATION_OUTPUT,
    DIAGNOSTICS_OUTPUT,
    ENSEMBLE_OUTPUT,
    ENSEMBLE_SIZE,
    FIGURES_DIR,
    FROZEN_STAGE3C_SHA256,
    FROZEN_STAGE4_SHA256,
    FROZEN_STAGE5_FULL_MANIFEST_SHA256,
    FROZEN_STAGE5_SHA256,
    FROZEN_STAGE5B_CORE_SHA256,
    FROZEN_STAGE5B_MANIFEST_SHA256,
    FROZEN_UPSTREAM_MANIFEST_SHA256,
    HOURLY_OUTPUT,
    HORIZONS,
    METRICS_OUTPUT,
    SELECTED_STAGE5_BY_HORIZON,
    STAGE2_INPUT,
    STAGE3C_INPUT,
    STAGE4_BASELINES,
    STAGE4_METRICS,
    STAGE4_REPORT,
    STAGE5_COMPARISON,
    STAGE5_CONTRACT,
    STAGE5_METRICS,
    STAGE5_PREDICTIONS,
)
from hackowatt_stage6a.ensemble import generate_member  # noqa: E402
from hackowatt_stage6a.pipeline import (  # noqa: E402
    frozen_fingerprints,
    main,
    stage5_manifest,
    stage5b_manifest,
    upstream_manifest,
)
from hackowatt_stage6a.policy import OptionalEventAwayPolicy, feasible_start_segments  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class SequenceRandom:
    def __init__(self, values: list[float]) -> None:
        self.values = iter(values)

    def random(self) -> float:
        return next(self.values)


class Stage6APeakRiskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = read_profile()
        cls.stage2 = read_csv(STAGE2_INPUT)
        cls.hourly = read_csv(HOURLY_OUTPUT)
        cls.frozen_predictions = read_csv(STAGE5_PREDICTIONS)
        cls.metrics = json.loads(METRICS_OUTPUT.read_text(encoding="utf-8"))
        cls.ensemble = np.load(ENSEMBLE_OUTPUT, allow_pickle=False)
        cls.index_by_time = {row["timestamp"]: index for index, row in enumerate(cls.stage2)}
        cls.schedules = origin_schedule(cls.profile)

    def _records(self, horizon: int) -> list[dict[str, str]]:
        return [row for row in self.hourly if int(row["horizon_hours"]) == horizon]

    def test_01_stage3c_frozen_artifact_unchanged(self) -> None:
        self.assertEqual(sha256(STAGE3C_INPUT), FROZEN_STAGE3C_SHA256)

    def test_02_stage4_artifacts_unchanged(self) -> None:
        self.assertEqual({
            "validation_metrics": sha256(STAGE4_METRICS),
            "baseline_metrics": sha256(STAGE4_BASELINES),
            "validation_report": sha256(STAGE4_REPORT),
        }, FROZEN_STAGE4_SHA256)

    def test_03_stage5_artifacts_unchanged(self) -> None:
        self.assertEqual({
            "predictions": sha256(STAGE5_PREDICTIONS),
            "metrics": sha256(STAGE5_METRICS),
            "comparison": sha256(STAGE5_COMPARISON),
            "contract": sha256(STAGE5_CONTRACT),
        }, FROZEN_STAGE5_SHA256)
        self.assertEqual(stage5_manifest()[0], FROZEN_STAGE5_FULL_MANIFEST_SHA256)

    def test_04_stage5b_artifacts_unchanged(self) -> None:
        processed = ROOT / "data" / "processed"
        self.assertEqual({
            "predictions": sha256(processed / "stage5b_peak_aware_predictions.csv"),
            "metrics": sha256(processed / "stage5b_peak_aware_metrics.json"),
            "comparison": sha256(processed / "stage5b_comparison.json"),
            "diagnostics": sha256(processed / "stage5b_peak_miss_diagnostics.csv"),
            "figure": sha256(ROOT / "artifacts" / "stage5b" / "168h_problem_window_comparison.svg"),
        }, FROZEN_STAGE5B_CORE_SHA256)
        self.assertEqual(stage5b_manifest()[0], FROZEN_STAGE5B_MANIFEST_SHA256)

    def test_05_fixed_seed_ensemble_generation_is_deterministic(self) -> None:
        first_times, first_demand, first_audit = generate_member(32)
        second_times, second_demand, second_audit = generate_member(32)
        self.assertEqual(first_times, second_times)
        np.testing.assert_array_equal(first_demand, second_demand)
        self.assertEqual(first_audit, second_audit)

    def test_06_evaluation_event_ledger_is_never_used(self) -> None:
        ensemble = self.metrics["ensemble"]
        self.assertFalse(ensemble["evaluation_realization_event_ledger_used"])
        self.assertEqual(ensemble["ensemble_input_scope"], [
            "frozen Stage 2 weather/calendar",
            "frozen Stage 3 generative rules",
            "deterministic member seeds",
        ])

    def test_07_future_evaluation_component_states_are_never_used(self) -> None:
        self.assertEqual(self.metrics["ensemble"]["evaluation_future_component_states_used"], [])

    def test_08_ensemble_uses_frozen_stage2_weather_calendar(self) -> None:
        self.assertEqual(self.metrics["ensemble"]["timeline_source"], "data/processed/stage2_barcelona_weather_solar_hourly.csv")
        self.assertEqual(self.metrics["ensemble"]["timeline_source_sha256"], sha256(STAGE2_INPUT))
        self.assertEqual([row["timestamp"] for row in self.stage2], [row["timestamp"] for row in self.profile])

    def test_09_exactly_200_complete_members_are_persisted(self) -> None:
        self.assertEqual(self.metrics["ensemble"]["size"], ENSEMBLE_SIZE)
        self.assertEqual(self.ensemble.shape, (200, 1464))
        self.assertEqual(self.metrics["ensemble"]["raw_trajectory_shape"], [200, 1464])
        self.assertEqual(len(self.metrics["ensemble"]["seed_pairs"]), 200)

    def test_10_quantiles_recompute_from_raw_ensemble(self) -> None:
        fields = {
            "ensemble_p05_kwh": 0.05,
            "ensemble_p10_kwh": 0.10,
            "ensemble_p25_kwh": 0.25,
            "ensemble_p50_kwh": 0.50,
            "ensemble_p75_kwh": 0.75,
            "ensemble_p90_kwh": 0.90,
            "ensemble_p95_kwh": 0.95,
        }
        for row in self.hourly[::37]:
            values = self.ensemble[:, self.index_by_time[row["timestamp"]]]
            self.assertAlmostEqual(float(row["ensemble_mean_kwh"]), float(np.mean(values)), places=12)
            self.assertAlmostEqual(float(row["ensemble_maximum_kwh"]), float(np.max(values)), places=12)
            for field, probability in fields.items():
                self.assertAlmostEqual(float(row[field]), float(np.quantile(values, probability)), places=12)

    def test_11_peak_threshold_uses_only_observations_through_origin(self) -> None:
        for origin_text, audit in self.metrics["peak_threshold"]["by_origin"].items():
            origin = datetime.fromisoformat(origin_text)
            available = [float(row["household_total_kwh"]) for row in self.profile if datetime.fromisoformat(row["timestamp"]) <= origin]
            self.assertEqual(audit["observations_at_or_before_origin"], len(available))
            self.assertAlmostEqual(audit["threshold_kwh"], float(np.percentile(available, 90)), places=12)
            self.assertEqual(audit["maximum_observed_timestamp"], origin_text)

    def test_12_peak_probability_recomputes_from_members(self) -> None:
        for row in self.hourly:
            values = self.ensemble[:, self.index_by_time[row["timestamp"]]]
            count = int(np.sum(values >= float(row["peak_threshold_kwh"])))
            self.assertEqual(int(row["ensemble_peak_member_count"]), count)
            self.assertAlmostEqual(float(row["peak_probability"]), count / 200, places=12)

    def test_13_actual_high_labels_use_origin_threshold(self) -> None:
        for row in self.hourly:
            expected = float(row["actual_household_kwh"]) >= float(row["peak_threshold_kwh"])
            self.assertEqual(row["actual_high_demand"] == "True", expected)

    def test_14_stage5_and_ensemble_timestamps_align_exactly(self) -> None:
        for horizon in HORIZONS:
            candidate = {(row["forecast_origin"], row["timestamp"]) for row in self._records(horizon)}
            frozen = {
                (row["forecast_origin"], row["timestamp"])
                for row in self.frozen_predictions
                if int(row["horizon_hours"]) == horizon and row["model"] == SELECTED_STAGE5_BY_HORIZON[horizon]
            }
            self.assertEqual(candidate, frozen)

    def test_15_top_risk_ranking_recomputes(self) -> None:
        for horizon in HORIZONS:
            by_origin: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in self._records(horizon):
                by_origin[row["forecast_origin"]].append(row)
            for window in by_origin.values():
                count = math.ceil(len(window) * 0.10)
                expected = {
                    row["timestamp"]
                    for row in sorted(window, key=lambda item: (-float(item["peak_probability"]), item["timestamp"]))[:count]
                }
                observed = {row["timestamp"] for row in window if row["top_10_percent_peak_risk"] == "True"}
                self.assertEqual(observed, expected)

    def test_16_interval_coverage_recomputes(self) -> None:
        for horizon in HORIZONS:
            records = self._records(horizon)
            p10_p90 = [float(row["ensemble_p10_kwh"]) <= float(row["actual_household_kwh"]) <= float(row["ensemble_p90_kwh"]) for row in records]
            p05_p95 = [float(row["ensemble_p05_kwh"]) <= float(row["actual_household_kwh"]) <= float(row["ensemble_p95_kwh"]) for row in records]
            saved = self.metrics["metrics_by_horizon"][str(horizon)]["intervals"]
            self.assertAlmostEqual(saved["p10_p90_coverage_percent"], sum(p10_p90) / len(records) * 100, places=9)
            self.assertAlmostEqual(saved["p05_p95_coverage_percent"], sum(p05_p95) / len(records) * 100, places=9)

    def test_17_no_stage1_through_stage5b_file_is_modified(self) -> None:
        self.assertEqual(upstream_manifest()[0], FROZEN_UPSTREAM_MANIFEST_SHA256)
        self.assertEqual(frozen_fingerprints()["all_stage1_through_stage5b_file_count"], 148)
        self.assertTrue(self.metrics["frozen_upstream_unchanged"])

    def test_18_stage6a_artifact_rebuild_is_byte_deterministic(self) -> None:
        tracked = [
            HOURLY_OUTPUT,
            METRICS_OUTPUT,
            DIAGNOSTICS_OUTPUT,
            CALIBRATION_OUTPUT,
            ENSEMBLE_OUTPUT,
            FIGURES_DIR / "168h_sep13_peak_risk.svg",
            FIGURES_DIR / "peak_probability_by_hour.svg",
            FIGURES_DIR / "interval_coverage.svg",
        ]
        before = {path: sha256(path) for path in tracked}
        self.assertEqual(main(reuse_existing_ensemble=True), 0)
        after = {path: sha256(path) for path in tracked}
        self.assertEqual(after, before)

    def test_19_suppression_requires_exhaustively_empty_start_support(self) -> None:
        for record in self.metrics["ensemble"]["optional_event_away_infeasibility_policy"]["suppression_records"]:
            away = [
                {
                    "event_id": interval["event_id"],
                    "start": datetime.fromisoformat(interval["start"]),
                    "end": datetime.fromisoformat(interval["end"]),
                }
                for interval in record["conflicting_away_intervals"]
            ]
            segments = feasible_start_segments(
                date.fromisoformat(record["date"]),
                record["permitted_start_lower_hour"],
                record["permitted_start_upper_hour"],
                record["sampled_duration_hours"],
                away,
            )
            self.assertEqual(segments, [])
            self.assertTrue(record["feasible_start_support_exhaustively_empty"])

    def test_20_feasible_conflicting_events_are_rescheduled_not_suppressed(self) -> None:
        day = date(2025, 8, 1)
        away = [{
            "event_id": "away_test",
            "start": datetime.fromisoformat("2025-08-01T09:00:00+02:00"),
            "end": datetime.fromisoformat("2025-08-01T11:00:00+02:00"),
        }]
        policy = OptionalEventAwayPolicy()
        start, initial, resampled, attempts = policy.random_start(
            SequenceRandom([0.2, 0.9]), day, 8.0, 14.0, 1.0, away, "pool heating"
        )
        self.assertTrue(resampled)
        self.assertEqual(attempts, 1)
        self.assertNotEqual(start, initial)
        self.assertGreaterEqual(start, away[0]["end"])
        self.assertEqual(policy.suppressions, [])

    def test_21_suppressed_events_allocate_exactly_zero_energy(self) -> None:
        day = date(2025, 8, 1)
        away = [{
            "event_id": "away_full",
            "start": datetime.fromisoformat("2025-08-01T07:00:00+02:00"),
            "end": datetime.fromisoformat("2025-08-01T20:00:00+02:00"),
        }]
        policy = OptionalEventAwayPolicy()
        start, _, _, _ = policy.random_start(SequenceRandom([]), day, 8.0, 14.0, 2.0, away, "sauna")
        target = [0.0] * 24
        allocations, energy = policy.allocate(start, start.replace(hour=10), 7.5, [], {}, target, start, start.replace(hour=23))
        self.assertEqual(allocations, [])
        self.assertEqual(energy, 0.0)
        self.assertEqual(target, [0.0] * 24)
        self.assertEqual(policy.suppressions[0]["allocated_energy_kwh"], 0.0)

    def test_22_suppression_preserves_draws_windows_away_and_seeds(self) -> None:
        records = self.metrics["ensemble"]["optional_event_away_infeasibility_policy"]["suppression_records"]
        self.assertGreater(len(records), 0)
        for record in records:
            self.assertGreater(record["sampled_duration_hours"], 0)
            self.assertGreater(record["sampled_power_kw"], 0)
            self.assertIn(record["permitted_start_range"], {"08:00-14:00", "19:00-22:00"})
            self.assertTrue(record["conflicting_away_intervals"])
            self.assertFalse(record["activation_redrawn"])
            self.assertFalse(record["duration_redrawn_or_shortened"])
            self.assertFalse(record["power_redrawn"])
            self.assertFalse(record["start_range_extended"])
            self.assertFalse(record["moved_to_another_day"])
            self.assertFalse(record["away_event_altered"])
            self.assertFalse(record["seed_substituted"])
            self.assertEqual(record["stage3a_seed"], 6_100_000 + 2 * record["member_index"])
            self.assertEqual(record["stage3b_seed"], 6_100_001 + 2 * record["member_index"])


if __name__ == "__main__":
    unittest.main()

