"""Independent Stage 10 PV economics tests."""

from __future__ import annotations

import csv
import hashlib
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

from hackowatt_stage10.config import (  # noqa: E402
    ANNUALIZED_OUTPUT,
    AUG_SEP_OUTPUT,
    CAPACITIES_KWP,
    CAPACITY_COMPARISON_OUTPUT,
    FIGURES_DIR,
    FROZEN_STAGE1_TO_STAGE9_FILE_COUNT,
    FROZEN_STAGE1_TO_STAGE9_TREE_SHA256,
    INSTALLATION_COST_EUR_PER_KWP,
    METHODOLOGY_DOC,
    SUMMARY_OUTPUT,
)
from hackowatt_stage10.pipeline import run  # noqa: E402
from hackowatt_stage10.validation import frozen_upstream_identity  # noqa: E402


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Stage10EconomicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.observed = read_csv(AUG_SEP_OUTPUT)
        cls.annualized = read_csv(ANNUALIZED_OUTPUT)
        cls.wide = read_csv(CAPACITY_COMPARISON_OUTPUT)
        cls.summary = json.loads(SUMMARY_OUTPUT.read_text(encoding="utf-8"))

    def test_01_required_artifacts_exist(self) -> None:
        for path in (AUG_SEP_OUTPUT, ANNUALIZED_OUTPUT, CAPACITY_COMPARISON_OUTPUT, SUMMARY_OUTPUT, METHODOLOGY_DOC):
            self.assertTrue(path.is_file(), path)

    def test_02_only_required_comparison_capacities_exist(self) -> None:
        self.assertEqual(tuple(float(row["capacity_kwp"]) for row in self.wide), CAPACITIES_KWP)
        self.assertTrue(self.summary["assumptions"]["capacities_are_comparisons_not_recommendations"])

    def test_03_stage8_annual_production_is_exact(self) -> None:
        expected = {3.0: 4677.03, 5.0: 7795.05, 8.0: 12472.08, 10.0: 15590.10}
        self.assertEqual({float(row["capacity_kwp"]): float(row["annual_pv_production_kwh"]) for row in self.wide}, expected)

    def test_04_observed_and_annualized_rows_are_separate(self) -> None:
        self.assertEqual(len(self.observed), 8)
        self.assertEqual(len(self.annualized), 8)
        self.assertTrue(all(row["provenance_label"] == "OBSERVED/FROZEN AUG-SEP" for row in self.observed))
        self.assertTrue(all(row["provenance_label"] == "ANNUALIZED ESTIMATE" for row in self.annualized))

    def test_05_five_kwp_reproduces_frozen_stage9(self) -> None:
        self.assertTrue(self.summary["validation"]["checks"]["frozen_stage9_5kwp_accounting_reproduced"])

    def test_06_current_and_optimized_share_pv_tariff_and_accounting(self) -> None:
        checks = self.summary["validation"]["checks"]
        self.assertTrue(checks["identical_pv_both_behaviors"])
        self.assertTrue(checks["identical_tariff_both_behaviors"])
        self.assertTrue(checks["identical_accounting_equations_both_behaviors"])

    def test_07_observed_energy_identities_hold(self) -> None:
        for row in self.observed:
            self.assertAlmostEqual(float(row["pv_generation_kwh"]), float(row["pv_self_consumed_kwh"]) + float(row["pv_exported_kwh"]), places=7)
            self.assertAlmostEqual(float(row["household_demand_kwh"]), float(row["pv_self_consumed_kwh"]) + float(row["grid_imported_kwh"]), places=7)

    def test_08_annual_energy_identities_hold(self) -> None:
        for row in self.annualized:
            self.assertAlmostEqual(float(row["annual_pv_production_kwh"]), float(row["annual_pv_self_consumed_kwh"]) + float(row["annual_pv_exported_kwh"]), places=6)
            self.assertAlmostEqual(float(row["annual_household_demand_kwh"]), float(row["annual_pv_self_consumed_kwh"]) + float(row["annual_grid_imported_kwh"]), places=6)

    def test_09_self_consumption_never_exceeds_generation_or_demand(self) -> None:
        for row in self.annualized:
            self.assertLessEqual(float(row["annual_pv_self_consumed_kwh"]), float(row["annual_pv_production_kwh"]) + 1e-7)
            self.assertLessEqual(float(row["annual_pv_self_consumed_kwh"]), float(row["annual_household_demand_kwh"]) + 1e-7)

    def test_10_grid_import_and_export_are_nonnegative(self) -> None:
        self.assertTrue(all(float(row["annual_grid_imported_kwh"]) >= 0 and float(row["annual_pv_exported_kwh"]) >= 0 for row in self.annualized))

    def test_11_self_consumption_rate_and_solar_coverage_are_distinct(self) -> None:
        for row in self.annualized:
            self_consumption = float(row["annual_pv_self_consumed_kwh"]) / float(row["annual_pv_production_kwh"])
            coverage = float(row["annual_pv_self_consumed_kwh"]) / float(row["annual_household_demand_kwh"])
            self.assertAlmostEqual(float(row["pv_self_consumption_rate"]), self_consumption, places=12)
            self.assertAlmostEqual(float(row["household_solar_coverage_rate"]), coverage, places=12)

    def test_12_investment_and_om_formulas_are_exact(self) -> None:
        for row in self.annualized:
            investment = float(row["capacity_kwp"]) * INSTALLATION_COST_EUR_PER_KWP
            self.assertEqual(float(row["initial_investment_eur"]), investment)
            self.assertEqual(float(row["annual_om_eur"]), investment * 0.01)

    def test_13_pv_benefit_uses_behavior_specific_no_pv_baseline(self) -> None:
        for row in self.annualized:
            expected = float(row["no_pv_annual_net_electricity_cost_eur"]) - float(row["annual_net_electricity_cost_eur"])
            self.assertAlmostEqual(float(row["gross_annual_electricity_benefit_eur"]), expected, places=9)

    def test_14_net_benefit_and_simple_payback_are_exact(self) -> None:
        for row in self.annualized:
            net = float(row["gross_annual_electricity_benefit_eur"]) - float(row["annual_om_eur"])
            self.assertAlmostEqual(float(row["net_annual_pv_benefit_eur"]), net, places=9)
            self.assertAlmostEqual(float(row["simple_payback_years"]), float(row["initial_investment_eur"]) / net, places=10)

    def test_15_annualization_is_symmetric(self) -> None:
        for capacity in CAPACITIES_KWP:
            rows = [row for row in self.annualized if float(row["capacity_kwp"]) == capacity]
            self.assertEqual(len({row["annualization_method"] for row in rows}), 1)
        self.assertEqual(self.summary["annualization"]["label"], "ANNUALIZED ESTIMATE")

    def test_16_behavioral_and_pv_effects_are_decomposed(self) -> None:
        decomposition = self.summary["effect_decomposition"]
        self.assertGreater(decomposition["behavioral_optimization_effect_no_pv_eur"], 0)
        self.assertTrue(all(row["gross_decomposition_identity_holds"] for row in decomposition["by_capacity"]))

    def test_17_optimization_does_not_change_investment_or_om(self) -> None:
        for row in self.wide:
            self.assertNotIn("current_initial_investment_eur", row)
            self.assertNotIn("optimized_initial_investment_eur", row)
            self.assertEqual(float(row["initial_investment_eur"]), float(row["capacity_kwp"]) * 1300)

    def test_18_calculation_rerun_is_deterministic(self) -> None:
        self.assertTrue(self.summary["determinism"]["identical_recalculation"])
        self.assertEqual(self.summary["determinism"]["calculation_sha256"], self.summary["determinism"]["repeat_sha256"])

    def test_19_artifact_rerun_is_byte_identical(self) -> None:
        paths = [AUG_SEP_OUTPUT, ANNUALIZED_OUTPUT, CAPACITY_COMPARISON_OUTPUT, SUMMARY_OUTPUT]
        paths += [FIGURES_DIR / name for name in (
            "annual_pv_production_vs_capacity.svg", "grid_import_vs_pv_capacity.svg",
            "pv_self_consumption_vs_capacity.svg", "annual_electricity_cost_vs_capacity.svg",
            "simple_payback_vs_capacity.svg", "current_vs_optimized_5kwp.svg",
        )]
        before = {path: sha256(path) for path in paths}
        run()
        after = {path: sha256(path) for path in paths}
        self.assertEqual(before, after)

    def test_20_all_figures_are_valid_svg(self) -> None:
        for path in FIGURES_DIR.glob("*.svg"):
            self.assertTrue(ET.parse(path).getroot().tag.endswith("svg"))
        self.assertEqual(len(list(FIGURES_DIR.glob("*.svg"))), 6)

    def test_21_frozen_stage1_through_stage9_are_unchanged(self) -> None:
        self.assertEqual(frozen_upstream_identity(), (FROZEN_STAGE1_TO_STAGE9_FILE_COUNT, FROZEN_STAGE1_TO_STAGE9_TREE_SHA256))
        self.assertTrue(self.summary["validation"]["frozen_upstream"]["byte_identical"])

    def test_22_no_mock_data_or_stage11_functionality(self) -> None:
        checks = self.summary["validation"]["checks"]
        self.assertTrue(checks["no_mock_data"])
        self.assertTrue(checks["no_stage11_started"])
        self.assertFalse((ROOT / "src/hackowatt_stage11").exists())

    def test_23_all_values_are_finite(self) -> None:
        for row in self.annualized:
            for key, value in row.items():
                if key not in {"provenance_label", "annualization_method", "behavior"}:
                    self.assertTrue(math.isfinite(float(value)), (key, value))

    def test_24_all_validation_gates_pass(self) -> None:
        validation = self.summary["validation"]
        self.assertEqual(validation["status"], "PASS", validation["problems"])
        self.assertGreaterEqual(len(validation["checks"]), 22)
        self.assertTrue(all(validation["checks"].values()))


if __name__ == "__main__":
    unittest.main()
