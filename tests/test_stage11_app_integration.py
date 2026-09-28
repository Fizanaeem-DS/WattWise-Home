"""Stage 11 real-artifact, contract, labeling, and immutability tests."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from pathlib import Path

from hackowatt_stage11.loader import ROOT, load_real_data
from hackowatt_stage11.models import Horizon, TARIFF_BANDS_EUR_PER_KWH
from hackowatt_stage11.validation import (
    FROZEN_STAGE1_TO_STAGE10_FILE_COUNT,
    FROZEN_STAGE1_TO_STAGE10_TREE_SHA256,
    frozen_upstream_identity,
    validate,
)


class Stage11IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_real_data()

    def test_01_all_required_real_artifacts_load(self) -> None:
        self.assertEqual(len(self.data.history), 1464)
        self.assertEqual(len(self.data.optimization.hourly), 1464)
        self.assertEqual(len(self.data.flexibility), 16)

    def test_02_no_final_section_uses_mock_or_partial_provenance(self) -> None:
        self.assertFalse(self.data.has_any_mock())
        self.assertTrue(all(item.source == "real" for item in self.data.all_provenance()))
        app_source = (ROOT / "app" / "data_source.py").read_text(encoding="utf-8")
        self.assertNotIn("mock_data", app_source)
        self.assertNotIn("generate_full_dataset", app_source)

    def test_03_history_timestamps_align_hourly_in_madrid(self) -> None:
        timestamps = [datetime.fromisoformat(point.timestamp) for point in self.data.history]
        self.assertEqual(len(timestamps), len(set(timestamps)))
        self.assertTrue(all(right - left == timedelta(hours=1) for left, right in zip(timestamps, timestamps[1:])))
        self.assertTrue(all(item.utcoffset() == timedelta(hours=2) for item in timestamps))

    def test_04_history_component_units_and_totals_are_kwh(self) -> None:
        for point in self.data.history:
            self.assertGreaterEqual(point.total_kwh, 0)
            self.assertAlmostEqual(point.total_kwh, sum(item.kwh for item in point.components), places=7)

    def test_05_forecast_horizons_map_exactly(self) -> None:
        self.assertEqual(set(self.data.forecasts), set(Horizon))
        for horizon in Horizon:
            bundle = self.data.forecasts[horizon]
            self.assertEqual(len(bundle.points), horizon.hours)
            self.assertEqual([point.lead_hour for point in bundle.points], list(range(1, horizon.hours + 1)))

    def test_06_expected_demand_and_uncertainty_are_distinct(self) -> None:
        for bundle in self.data.forecasts.values():
            self.assertAlmostEqual(bundle.total_expected_kwh, sum(point.expected_kwh for point in bundle.points))
            self.assertTrue(all(point.p10_kwh <= point.p90_kwh <= point.p95_kwh for point in bundle.points))

    def test_07_peak_probabilities_and_labels_map_exactly(self) -> None:
        for bundle in self.data.forecasts.values():
            for point in bundle.points:
                expected = "LOW" if point.peak_probability < .20 else "MEDIUM" if point.peak_probability < .40 else "HIGH"
                self.assertEqual(point.peak_risk_label, expected)

    def test_08_stage6b_explanations_are_present_not_generated_in_app(self) -> None:
        self.assertTrue(all(point.primary_explanation for bundle in self.data.forecasts.values() for point in bundle.points))
        app_source = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
        self.assertIn("point.primary_explanation", app_source)

    def test_09_official_tariff_is_the_only_tariff(self) -> None:
        self.assertEqual(TARIFF_BANDS_EUR_PER_KWH, ((0, 6, .18), (6, 17, .28), (17, 22, .40), (22, 24, .28)))
        for bundle in self.data.forecasts.values():
            for point in bundle.points:
                hour = datetime.fromisoformat(point.timestamp).hour
                price = next(price for start, end, price in TARIFF_BANDS_EUR_PER_KWH if start <= hour < end)
                self.assertEqual(point.tariff_eur_per_kwh, price)

    def test_10_flexibility_abcd_classes_and_real_instances(self) -> None:
        counts = {name: sum(item.flexibility_class.value == name for item in self.data.flexibility) for name in ("fixed", "behavior_driven", "limited", "shiftable")}
        self.assertEqual(counts, {"fixed": 3, "behavior_driven": 4, "limited": 3, "shiftable": 6})
        self.assertTrue(all(item.actual_event_count == 0 or item.actual_energy_min_kwh is not None for item in self.data.flexibility))

    def test_11_stage9_current_and_optimized_metrics_reproduce(self) -> None:
        summary = self.data.optimization.summary["aug_sep"]
        hourly = self.data.optimization.hourly
        self.assertAlmostEqual(sum(point.current_grid_import_kwh for point in hourly), summary["current_grid_import_kwh"], places=6)
        self.assertAlmostEqual(sum(point.optimized_grid_import_kwh for point in hourly), summary["optimized_grid_import_kwh"], places=6)
        self.assertAlmostEqual(sum(point.current_net_cost_eur for point in hourly), summary["current_net_electricity_cost_eur"], places=6)
        self.assertAlmostEqual(sum(point.optimized_net_cost_eur for point in hourly), summary["optimized_net_electricity_cost_eur"], places=6)
        self.assertEqual(len(self.data.optimization.shifted_events), summary["number_of_shifted_events"])

    def test_12_stage10_metrics_reproduce_frozen_values(self) -> None:
        decomposition = {float(row["capacity_kwp"]): row for row in self.data.pv.effect_decomposition["by_capacity"]}
        for row in self.data.pv.rows:
            self.assertAlmostEqual(row.optimized["net_annual_pv_benefit_eur"], decomposition[row.capacity_kwp]["pv_effect_optimized_habits_net_after_om_eur"])

    def test_13_all_four_and_only_approved_pv_capacities_work(self) -> None:
        self.assertEqual([row.capacity_kwp for row in self.data.pv.rows], [3.0, 5.0, 8.0, 10.0])

    def test_14_annualized_and_simple_payback_labels_are_exact(self) -> None:
        self.assertEqual(self.data.pv.annualized_label, "ANNUALIZED ESTIMATE")
        self.assertEqual(self.data.pv.payback_label, "SIMPLE PAYBACK")
        app_source = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
        self.assertIn("ANNUALIZED ESTIMATE", app_source)
        self.assertIn("SIMPLE PAYBACK", app_source)

    def test_15_behavioral_and_pv_benefits_remain_separate(self) -> None:
        self.assertTrue(all(row["gross_decomposition_identity_holds"] for row in self.data.pv.effect_decomposition["by_capacity"]))

    def test_16_app_preserves_all_eight_ivana_pages(self) -> None:
        source = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
        for page in ("Overview", "Historical Consumption", "Forecast", "Peak Hours", "Tariff", "Flexibility (Stage 7)", "PV Simulator", "Optimizer"):
            self.assertIn(f'"{page}"', source)

    def test_17_missing_real_data_fails_closed_no_mock_fallback(self) -> None:
        source = (ROOT / "src" / "hackowatt_stage11" / "loader.py").read_text(encoding="utf-8")
        self.assertIn("Required REAL Stage 11 source artifact(s) missing", source)
        self.assertNotIn("mock_data", source)

    def test_18_frozen_stages1_through10_are_byte_identical(self) -> None:
        count, tree_hash = frozen_upstream_identity()
        self.assertEqual(count, FROZEN_STAGE1_TO_STAGE10_FILE_COUNT)
        self.assertEqual(tree_hash, FROZEN_STAGE1_TO_STAGE10_TREE_SHA256)

    def test_19_all_independent_validation_gates_pass(self) -> None:
        report = validate()
        self.assertEqual(report["status"], "PASS", report["problems"])
        self.assertTrue(all(report["checks"].values()))


if __name__ == "__main__":
    unittest.main()
