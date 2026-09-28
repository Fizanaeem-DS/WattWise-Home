"""Independent contract, provenance, ranking, and determinism tests for Stage 6B."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hackowatt_stage6b.config import (  # noqa: E402
    EXPLAINED_OUTPUT,
    FIGURES_DIR,
    FROZEN_STAGE1_TO_STAGE6A_MANIFEST_SHA256,
    FROZEN_STAGE6A_MANIFEST_SHA256,
    OUTPUT_COLUMNS,
    STAGE5_PREDICTIONS,
    STAGE6A_HOURLY,
    SUMMARIES_OUTPUT,
)
from hackowatt_stage6b.explanations import explanations, risk_label, tariff  # noqa: E402
from hackowatt_stage6b.pipeline import (  # noqa: E402
    run,
    stage6a_manifest,
    upstream_manifest,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Stage6BOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.output = read_csv(EXPLAINED_OUTPUT)
        cls.stage5 = read_csv(STAGE5_PREDICTIONS)
        cls.stage6a = read_csv(STAGE6A_HOURLY)
        cls.contract = json.loads(SUMMARIES_OUTPUT.read_text(encoding="utf-8"))
        cls.summaries = cls.contract["summaries"]
        cls.stage5_lookup = {
            (int(row["horizon_hours"]), row["forecast_origin"], row["timestamp"], row["model"]): row
            for row in cls.stage5
        }
        cls.stage6a_lookup = {
            (int(row["horizon_hours"]), row["forecast_origin"], row["timestamp"]): row
            for row in cls.stage6a
        }
        cls.output_windows: dict[tuple[int, str], list[dict[str, str]]] = defaultdict(list)
        for row in cls.output:
            cls.output_windows[(int(row["horizon_hours"]), row["forecast_origin"])].append(row)

    def test_01_schema_and_complete_window_counts(self) -> None:
        self.assertEqual(len(self.output), 2232)
        self.assertEqual(tuple(self.output[0]), OUTPUT_COLUMNS)
        self.assertEqual(len(self.output_windows), 27)
        self.assertEqual(Counter(int(row["horizon_hours"]) for row in self.summaries), {24: 10, 72: 9, 168: 8})

    def test_02_every_point_forecast_exactly_matches_frozen_stage5(self) -> None:
        for row in self.output:
            key = (
                int(row["horizon_hours"]), row["forecast_origin"], row["timestamp"], row["stage5_selected_model"]
            )
            self.assertEqual(float(row["point_forecast_kwh"]), float(self.stage5_lookup[key]["predicted_household_kwh"]))

    def test_03_every_quantile_exactly_matches_frozen_stage6a(self) -> None:
        mapping = {
            "p10_kwh": "ensemble_p10_kwh",
            "p50_kwh": "ensemble_p50_kwh",
            "p90_kwh": "ensemble_p90_kwh",
            "p95_kwh": "ensemble_p95_kwh",
        }
        for row in self.output:
            source = self.stage6a_lookup[(int(row["horizon_hours"]), row["forecast_origin"], row["timestamp"])]
            for output_field, source_field in mapping.items():
                self.assertEqual(float(row[output_field]), float(source[source_field]))

    def test_04_probability_and_threshold_exactly_match_stage6a(self) -> None:
        for row in self.output:
            source = self.stage6a_lookup[(int(row["horizon_hours"]), row["forecast_origin"], row["timestamp"])]
            self.assertEqual(float(row["peak_probability"]), float(source["peak_probability"]))
            self.assertEqual(float(row["peak_threshold_kwh"]), float(source["peak_threshold_kwh"]))

    def test_05_actual_and_hidden_future_state_are_not_in_contract(self) -> None:
        forbidden = {
            "actual_household_kwh", "actual_high_demand", "event_ledger", "occupancy_state",
            "guest_event", "ev1_charging_kwh", "ev2_charging_kwh", "sauna_kwh", "pool_heating_kwh",
        }
        self.assertTrue(forbidden.isdisjoint(self.output[0]))
        self.assertFalse(self.contract["operational_output_uses_actual_demand"])
        valid = {
            "hour": 19, "behavioral_block": "EVENING", "is_weekend": True,
            "temperature_2m": 27.0, "point_forecast_kwh": 3.0, "peak_probability": 0.5,
            "peak_risk_label": "HIGH", "tariff_period": "PEAK_17_22", "tariff_eur_per_kwh": 0.40,
        }
        with self.assertRaises(ValueError):
            explanations({**valid, "actual_household_kwh": 4.2})
        with self.assertRaises(ValueError):
            explanations({**valid, "event_ledger": []})

    def test_06_risk_labels_follow_exact_display_boundaries(self) -> None:
        self.assertEqual(risk_label(0.0), "LOW")
        self.assertEqual(risk_label(0.199999), "LOW")
        self.assertEqual(risk_label(0.20), "MEDIUM")
        self.assertEqual(risk_label(0.399999), "MEDIUM")
        self.assertEqual(risk_label(0.40), "HIGH")
        self.assertEqual(risk_label(1.0), "HIGH")
        for row in self.output:
            self.assertEqual(row["peak_risk_label"], risk_label(float(row["peak_probability"])))
        self.assertTrue(self.contract["risk_label_thresholds_are_presentation_only"])

    def test_07_expected_and_risk_rankings_recompute_exactly(self) -> None:
        by_summary = {(int(row["horizon_hours"]), row["forecast_origin"]): row for row in self.summaries}
        for key, window in self.output_windows.items():
            summary = by_summary[key]
            expected = sorted(window, key=lambda row: (
                -float(row["point_forecast_kwh"]), -float(row["peak_probability"]), row["timestamp"]
            ))
            risk = sorted(window, key=lambda row: (
                -float(row["peak_probability"]), -float(row["p95_kwh"]),
                -float(row["point_forecast_kwh"]), row["timestamp"]
            ))
            self.assertEqual(
                [item["timestamp"] for item in summary["top_5_expected_demand_hours"]],
                [row["timestamp"] for row in expected[:5]],
            )
            self.assertEqual(
                [item["timestamp"] for item in summary["top_5_peak_risk_hours"]],
                [row["timestamp"] for row in risk[:5]],
            )
            self.assertEqual(summary["highest_expected_demand_hour"], expected[0]["timestamp"])
            self.assertEqual(summary["highest_peak_risk_hour"], risk[0]["timestamp"])

    def test_08_each_top_list_has_five_distinct_valid_timestamps(self) -> None:
        for summary in self.summaries:
            key = (int(summary["horizon_hours"]), summary["forecast_origin"])
            valid = {row["timestamp"] for row in self.output_windows[key]}
            for field in ("top_5_expected_demand_hours", "top_5_peak_risk_hours"):
                timestamps = [item["timestamp"] for item in summary[field]]
                self.assertEqual(len(timestamps), 5)
                self.assertEqual(len(set(timestamps)), 5)
                self.assertTrue(set(timestamps) <= valid)

    def test_09_total_expected_energy_is_stage5_point_sum(self) -> None:
        by_summary = {(int(row["horizon_hours"]), row["forecast_origin"]): row for row in self.summaries}
        for key, window in self.output_windows.items():
            expected = sum(float(row["point_forecast_kwh"]) for row in window)
            self.assertEqual(by_summary[key]["total_expected_energy_kwh"], expected)

    def test_10_tariff_mapping_follows_frozen_assumptions(self) -> None:
        self.assertEqual(tariff(0), (0.18, "OFF_PEAK_00_06"))
        self.assertEqual(tariff(5), (0.18, "OFF_PEAK_00_06"))
        self.assertEqual(tariff(6), (0.28, "STANDARD_06_17"))
        self.assertEqual(tariff(16), (0.28, "STANDARD_06_17"))
        self.assertEqual(tariff(17), (0.40, "PEAK_17_22"))
        self.assertEqual(tariff(21), (0.40, "PEAK_17_22"))
        self.assertEqual(tariff(22), (0.28, "STANDARD_22_24"))
        self.assertEqual(tariff(23), (0.28, "STANDARD_22_24"))
        for row in self.output:
            price, period = tariff(datetime.fromisoformat(row["timestamp"]).hour)
            self.assertEqual((float(row["tariff_eur_per_kwh"]), row["tariff_period"]), (price, period))

    def test_11_provenance_sources_are_explicit_and_stage5b_is_not_used(self) -> None:
        for row in self.output:
            self.assertEqual(row["point_forecast_source"], "stage5_frozen_selected_model")
            self.assertEqual(row["risk_quantile_source"], "stage6a_frozen_ensemble")
            self.assertEqual(row["explanation_source"], "stage6b_deterministic_rules")
            self.assertEqual(row["provenance"], "real")
        serialized = EXPLAINED_OUTPUT.read_text(encoding="utf-8") + SUMMARIES_OUTPUT.read_text(encoding="utf-8")
        self.assertNotIn("stage5b", serialized.lower())

    def test_12_explanations_are_short_probabilistic_and_deterministic(self) -> None:
        forbidden_claims = ("will happen", "will turn on", "will operate")
        for row in self.output:
            for field in ("primary_explanation", "secondary_explanation"):
                self.assertNotIn("\n", row[field])
                self.assertLessEqual(len(row[field]), 180)
                for claim in forbidden_claims:
                    self.assertNotIn(claim, row[field].lower())

    def test_13_deterministic_rerun_is_byte_identical(self) -> None:
        paths = [
            EXPLAINED_OUTPUT,
            SUMMARIES_OUTPUT,
            FIGURES_DIR / "168h_explained_forecast_demo.svg",
        ]
        before = {path: sha256(path) for path in paths}
        run()
        first = {path: sha256(path) for path in paths}
        run()
        second = {path: sha256(path) for path in paths}
        self.assertEqual(before, first)
        self.assertEqual(first, second)

    def test_14_all_stage1_through_stage6a_artifacts_remain_unchanged(self) -> None:
        self.assertEqual(stage6a_manifest()[0], FROZEN_STAGE6A_MANIFEST_SHA256)
        self.assertEqual(upstream_manifest()[0], FROZEN_STAGE1_TO_STAGE6A_MANIFEST_SHA256)
        self.assertEqual(
            self.contract["frozen_upstream"]["stage1_to_stage6a_manifest_sha256"],
            FROZEN_STAGE1_TO_STAGE6A_MANIFEST_SHA256,
        )

    def test_15_demo_is_only_retrospective_actual_use_and_later_stages_not_started(self) -> None:
        svg = (FIGURES_DIR / "168h_explained_forecast_demo.svg").read_text(encoding="utf-8")
        self.assertIn("Actual demand is retrospective evaluation truth only", svg)
        self.assertEqual(self.contract["p95_label"], "high-demand potential (P95)")
        self.assertFalse(self.contract["stage7_started"])
        self.assertFalse(self.contract["stage8_started"])
        self.assertFalse(self.contract["stage9_started"])


if __name__ == "__main__":
    unittest.main()
