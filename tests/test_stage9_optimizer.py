"""Independent artifact and contract tests for Stage 9."""

from __future__ import annotations

import csv
from datetime import datetime
import json
import math
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "stage7" / "backend"))

from hackowatt_stage9.accounting import account_hour  # noqa: E402
from hackowatt_stage9.config import (  # noqa: E402
    APP_CONTRACT_DOC,
    EVENT_OUTPUT,
    FIGURES_DIR,
    HOURLY_OUTPUT,
    METHODOLOGY_DOC,
    SUMMARY_OUTPUT,
)
from hackowatt_stage9.data import build_operational_context  # noqa: E402
from hackowatt_stage9.validation import frozen_upstream_identity  # noqa: E402


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class Stage9OptimizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.hourly = read_csv(HOURLY_OUTPUT)
        cls.events = read_csv(EVENT_OUTPUT)
        cls.summary = json.loads(SUMMARY_OUTPUT.read_text(encoding="utf-8"))

    def test_01_required_outputs_exist(self) -> None:
        for path in (HOURLY_OUTPUT, EVENT_OUTPUT, SUMMARY_OUTPUT, METHODOLOGY_DOC, APP_CONTRACT_DOC):
            self.assertTrue(path.is_file(), path)

    def test_02_hourly_contract_is_complete_and_aligned(self) -> None:
        self.assertEqual(len(self.hourly), 1464)
        self.assertEqual(self.hourly[0]["timestamp"], "2025-08-01T00:00:00+02:00")
        self.assertEqual(self.hourly[-1]["timestamp"], "2025-09-30T23:00:00+02:00")
        required = {
            "current_load_kwh", "optimized_load_kwh", "pv_generation_kwh", "tariff_eur_per_kwh",
            "current_self_consumed_pv_kwh", "optimized_self_consumed_pv_kwh",
            "current_grid_import_kwh", "optimized_grid_import_kwh",
            "current_exported_pv_kwh", "optimized_exported_pv_kwh",
            "current_net_cost_eur", "optimized_net_cost_eur", "current_peak_risk",
            "stage6_expected_demand_kwh",
        }
        self.assertTrue(required.issubset(self.hourly[0]))

    def test_03_current_and_optimized_use_exact_shared_accounting(self) -> None:
        for row in self.hourly:
            for prefix in ("current", "optimized"):
                expected = account_hour(
                    float(row[f"{prefix}_load_kwh"]),
                    float(row["pv_generation_kwh"]),
                    float(row["tariff_eur_per_kwh"]),
                )
                self.assertAlmostEqual(float(row[f"{prefix}_grid_import_kwh"]), expected["grid_import_kwh"], places=8)
                self.assertAlmostEqual(float(row[f"{prefix}_exported_pv_kwh"]), expected["exported_pv_kwh"], places=8)
                self.assertAlmostEqual(float(row[f"{prefix}_net_cost_eur"]), expected["net_cost_eur"], places=8)

    def test_04_energy_flows_and_loads_are_nonnegative(self) -> None:
        fields = (
            "current_load_kwh", "optimized_load_kwh", "pv_generation_kwh",
            "current_self_consumed_pv_kwh", "optimized_self_consumed_pv_kwh",
            "current_grid_import_kwh", "optimized_grid_import_kwh",
            "current_exported_pv_kwh", "optimized_exported_pv_kwh",
        )
        self.assertTrue(all(float(row[field]) >= -1e-8 for row in self.hourly for field in fields))

    def test_05_every_stage7_event_is_explicit(self) -> None:
        non_hvac = [row for row in self.events if row["component"] != "hvac"]
        self.assertEqual(len(non_hvac), 177)
        self.assertEqual(len({row["event_id"] for row in non_hvac}), 177)
        self.assertEqual(self.summary["boundary_outside_window_events"], ["ev2_charge_026"])
        self.assertEqual(self.summary["infeasible_events"], [])

    def test_06_non_hvac_service_energy_is_preserved(self) -> None:
        for row in self.events:
            if row["constraint_status"] == "satisfied":
                self.assertAlmostEqual(float(row["original_energy_kwh"]), float(row["optimized_energy_kwh"]), places=5)
        self.assertTrue(self.summary["service_preservation"]["non_hvac_energy_preserved"])

    def test_07_coherent_events_preserve_duration_and_power(self) -> None:
        coherent = [row for row in self.events if row["coherent_cycle"].lower() == "true"]
        self.assertGreater(len(coherent), 0)
        for row in coherent:
            start, end = datetime.fromisoformat(row["optimized_start"]), datetime.fromisoformat(row["optimized_end"])
            self.assertAlmostEqual((end - start).total_seconds() / 3600, float(row["duration_hours"]), places=7)
            self.assertAlmostEqual(float(row["energy_kwh"]), float(row["power_kw"]) * float(row["duration_hours"]), places=5)

    def test_08_washer_dryer_dependencies_are_ordered(self) -> None:
        by_id = {row["event_id"]: row for row in self.events}
        for row in self.events:
            if row["depends_on_event_id"]:
                self.assertGreaterEqual(
                    datetime.fromisoformat(row["optimized_start"]),
                    datetime.fromisoformat(by_id[row["depends_on_event_id"]]["optimized_end"]),
                )

    def test_09_comfort_infeasibility_is_proven_and_minimized(self) -> None:
        comfort = self.summary["comfort"]
        self.assertEqual(comfort["physically_infeasible_occupied_hour_count"], 42)
        self.assertTrue(comfort["zero_avoidable_comfort_violation_introduced"])
        example = next(item for item in comfort["minimum_unavoidable_violations"] if item["timestamp"] == "2025-08-10T17:00:00+02:00")
        self.assertAlmostEqual(example["minimum_unavoidable_violation_c"], 0.112312094, places=7)
        self.assertAlmostEqual(comfort["total_unavoidable_degree_hours"], 36.986021822583936, places=8)

    def test_10_controller_targets_are_not_documented_as_hard_empty_away_bounds(self) -> None:
        text = METHODOLOGY_DOC.read_text(encoding="utf-8")
        self.assertIn("controller targets", text)
        self.assertIn("not hard indoor-temperature bounds", text)
        self.assertIn("natural thermal drift", text)

    def test_11_lexicographic_cost_and_peak_priority_is_recorded(self) -> None:
        objective = self.summary["objective_priority"]
        self.assertIn("comfort", objective[0])
        self.assertIn("net electricity cost", objective[1])
        self.assertIn("peak", objective[2])
        values = self.summary["solver_objectives"]
        self.assertLessEqual(values["final_net_cost_eur"], values["minimum_net_cost_before_peak_tiebreak_eur"] + 1.1e-5)

    def test_12_all_independent_validation_gates_pass(self) -> None:
        validation = self.summary["validation"]
        self.assertEqual(validation["status"], "PASS", validation["problems"])
        self.assertTrue(all(validation["checks"].values()), validation["checks"])

    def test_13_second_full_solve_is_identical(self) -> None:
        determinism = self.summary["determinism"]
        self.assertTrue(determinism["verified_by_full_second_solve"])
        self.assertTrue(determinism["identical_schedule"])
        self.assertEqual(determinism["schedule_sha256"], determinism["rerun_schedule_sha256"])

    def test_14_operational_mode_has_no_future_actual_leakage(self) -> None:
        context = build_operational_context("2025-09-01T23:00:00+02:00", 24, 5.0)
        self.assertFalse(context["uses_future_actual_demand"])
        self.assertEqual(len(context["points"]), 24)
        self.assertNotIn("actual_demand_kwh", context["points"][0])

    def test_15_frozen_stage1_through_stage8_are_byte_identical(self) -> None:
        count, digest = frozen_upstream_identity()
        frozen = self.summary["validation"]["frozen_upstream"]
        self.assertEqual(count, frozen["expected_file_count"])
        self.assertEqual(digest, frozen["expected_tree_sha256"])
        self.assertTrue(frozen["byte_identical"])

    def test_16_figures_are_valid_svg(self) -> None:
        for name in (
            "representative_week_current_vs_optimized.svg",
            "representative_week_grid_import.svg",
            "representative_week_cost.svg",
        ):
            root = ET.parse(FIGURES_DIR / name).getroot()
            self.assertTrue(root.tag.endswith("svg"))

    def test_17_summary_numbers_are_finite_and_economically_ordered(self) -> None:
        totals = self.summary["aug_sep"]
        self.assertTrue(all(math.isfinite(value) for value in totals.values()))
        self.assertGreater(totals["savings_eur"], 0)
        self.assertGreater(totals["peak_reduction_kwh"], 0)
        self.assertGreater(totals["optimized_pv_self_consumption_kwh"], totals["current_pv_self_consumption_kwh"])

    def test_18_reference_capacity_is_not_a_recommendation(self) -> None:
        self.assertEqual(self.summary["reference_capacity_kwp"], 5.0)
        self.assertFalse(self.summary["reference_capacity_is_recommendation"])


if __name__ == "__main__":
    unittest.main()
