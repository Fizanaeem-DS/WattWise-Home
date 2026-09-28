"""Independent end-to-end tests for the final WattWise product audit."""

from __future__ import annotations

import unittest

from hackowatt_stage11 import load_real_data
from hackowatt_stage11.models import Horizon
from hackowatt_stage12.audit import (
    FINAL_STAGE1_TO_STAGE11_FILE_COUNT,
    FINAL_STAGE1_TO_STAGE11_TREE_SHA256,
    audit_system,
    frozen_stage1_to_stage11_identity,
)


class Stage12EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_real_data()
        cls.audit = audit_system()

    def test_01_final_stage1_to_stage11_freeze(self) -> None:
        self.assertEqual(frozen_stage1_to_stage11_identity(), (FINAL_STAGE1_TO_STAGE11_FILE_COUNT, FINAL_STAGE1_TO_STAGE11_TREE_SHA256))

    def test_02_no_mock_or_partial_data(self) -> None:
        self.assertFalse(self.data.has_any_mock())

    def test_03_all_contract_numbers_are_finite(self) -> None:
        self.assertTrue(self.audit["checks"]["all_app_contract_numbers_finite"])

    def test_04_historical_exact_totals(self) -> None:
        metrics = self.audit["metrics"]["historical"]
        self.assertEqual(metrics["hours"], 1464)
        self.assertAlmostEqual(metrics["total_kwh"], 2834.740433147, places=9)
        self.assertAlmostEqual(metrics["maximum_hourly_kwh"], 21.699169197, places=9)

    def test_05_historical_context_and_components(self) -> None:
        for key in ("historical_components_reconcile", "historical_context_fields_map", "historical_exact_period_and_timezone"):
            self.assertTrue(self.audit["checks"][key])

    def test_06_all_forecast_horizons_exact(self) -> None:
        self.assertEqual({horizon.value: len(self.data.forecasts[horizon].points) for horizon in Horizon}, {"24h": 24, "72h": 72, "168h": 168})
        self.assertTrue(self.audit["checks"]["forecast_models_exact_by_horizon"])
        self.assertTrue(self.audit["checks"]["forecast_point_quantiles_temperature_exact"])

    def test_07_expected_energy_and_highest_hours_exact(self) -> None:
        self.assertTrue(self.audit["checks"]["forecast_total_expected_energy_exact"])
        self.assertTrue(self.audit["checks"]["highest_expected_hour_exact"])

    def test_08_peak_risk_values_labels_and_ranking_exact(self) -> None:
        for key in ("peak_probabilities_exact", "peak_labels_exact_boundaries", "p95_is_high_demand_potential", "high_risk_ranking_exact", "no_deterministic_peak_claim"):
            self.assertTrue(self.audit["checks"][key])

    def test_09_explanations_map_to_displayed_hours(self) -> None:
        self.assertTrue(self.audit["checks"]["explanations_map_exactly"])

    def test_10_tariff_boundaries_and_cross_stage_identity(self) -> None:
        for key in ("tariff_boundaries_exact", "stage9_tariff_identical", "stage10_tariff_identical"):
            self.assertTrue(self.audit["checks"][key])

    def test_11_stage7_production_constraints_complete(self) -> None:
        for key in ("stage7_production_source_real", "stage7_energy_duration_power_valid", "stage7_dependencies_resolve", "stage7_ev_availability_complete", "stage7_actual_events_away_compatible", "stage7_boundary_accounting_explicit"):
            self.assertTrue(self.audit["checks"][key])

    def test_12_stage9_current_and_optimized_exact(self) -> None:
        for key in ("stage9_current_values_exact", "stage9_optimized_values_exact", "stage9_derived_impacts_exact", "stage9_shifted_event_display_exact"):
            self.assertTrue(self.audit["checks"][key])

    def test_13_service_and_comfort_claims_supported(self) -> None:
        self.assertTrue(self.audit["checks"]["stage9_service_preservation_supported"])
        self.assertTrue(self.audit["checks"]["stage9_comfort_claim_exact"])
        self.assertTrue(self.audit["metrics"]["comfort"]["zero_avoidable_violation"])

    def test_14_stage8_pv_production_exact(self) -> None:
        self.assertEqual(self.audit["metrics"]["pv_annual_kwh"], {3.0: 4677.03, 5.0: 7795.05, 8.0: 12472.08, 10.0: 15590.10})

    def test_15_stage10_methodology_and_labels_exact(self) -> None:
        for key in ("stage10_all_rows_annualized_labeled", "stage10_methodology_exact", "annualized_and_payback_labels_visible"):
            self.assertTrue(self.audit["checks"][key])

    def test_16_stage10_five_kwp_values_exact(self) -> None:
        self.assertTrue(self.audit["checks"]["stage10_five_kwp_exact"])

    def test_17_all_stage10_capacities_reproduce_app(self) -> None:
        self.assertTrue(self.audit["checks"]["stage10_all_capacities_reproduce_app"])

    def test_18_behavioral_and_pv_savings_are_separate(self) -> None:
        self.assertAlmostEqual(self.audit["metrics"]["behavioral_optimization_no_pv_eur_per_year"], 1162.519476004677)
        self.assertTrue(self.audit["checks"]["savings_decomposition_exact"])

    def test_19_provenance_and_claims_are_clear(self) -> None:
        for key in ("no_mock_fallback_in_app", "synthetic_household_claim_clear", "all_major_limitations_visible"):
            self.assertTrue(self.audit["checks"][key])

    def test_20_current_and_optimized_are_not_swapped(self) -> None:
        self.assertTrue(self.audit["checks"]["current_and_optimized_not_swapped"])

    def test_21_all_eight_pages_present(self) -> None:
        self.assertTrue(self.audit["checks"]["all_eight_pages_present"])

    def test_22_every_stage12_gate_passes(self) -> None:
        self.assertEqual(self.audit["status"], "PASS", self.audit["problems"])
        self.assertTrue(all(self.audit["checks"].values()))


if __name__ == "__main__":
    unittest.main()
