"""Independent provenance, scaling, alignment, and scope tests for Stage 8."""

from __future__ import annotations

import ast
import csv
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hackowatt_stage8 import get_annual_pv_summary, get_pv_generation  # noqa: E402
from hackowatt_stage8.config import (  # noqa: E402
    DEMO_CAPACITIES_KWP,
    EXAMPLES_OUTPUT,
    FIGURES_DIR,
    FROZEN_UPSTREAM_FILE_COUNT,
    FROZEN_UPSTREAM_MANIFEST_SHA256,
    HOURLY_OUTPUT,
    MONTHLY_OUTPUT,
    RAW_OUTPUT,
    REFERENCE_CAPACITY_KWP,
    STAGE2_INPUT,
    VALIDATION_OUTPUT,
)
from hackowatt_stage8.pipeline import run, upstream_manifest  # noqa: E402


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Stage8PVTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.hourly = read_csv(HOURLY_OUTPUT)
        cls.monthly = read_csv(MONTHLY_OUTPUT)
        cls.stage2 = read_csv(STAGE2_INPUT)
        cls.examples = json.loads(EXAMPLES_OUTPUT.read_text(encoding="utf-8"))
        cls.validation = json.loads(VALIDATION_OUTPUT.read_text(encoding="utf-8"))
        cls.raw = json.loads(RAW_OUTPUT.read_text(encoding="utf-8"))

    def test_01_all_frozen_stage1_through_stage6b_files_are_unchanged(self) -> None:
        digest, files = upstream_manifest()
        self.assertEqual(len(files), FROZEN_UPSTREAM_FILE_COUNT)
        self.assertEqual(digest, FROZEN_UPSTREAM_MANIFEST_SHA256)
        self.assertEqual(self.validation["frozen_upstream"]["manifest_sha256"], digest)

    def test_02_normalized_reference_capacity_is_exactly_one_kwp(self) -> None:
        self.assertEqual(REFERENCE_CAPACITY_KWP, 1.0)
        self.assertEqual(self.examples["reference_system"]["capacity_kwp"], 1.0)
        self.assertTrue(all(float(row["reference_capacity_kwp"]) == 1.0 for row in self.hourly))
        self.assertTrue(all(float(row["reference_capacity_kwp"]) == 1.0 for row in self.monthly))

    def test_03_hourly_pv_generation_is_nonnegative(self) -> None:
        self.assertTrue(all(float(row["pv_generation_kwh_per_kwp"]) >= 0 for row in self.hourly))
        self.assertTrue(self.validation["all_nonnegative"])

    def test_04_required_aug_sep_output_has_exactly_1464_hours(self) -> None:
        self.assertEqual(len(self.hourly), 1464)
        self.assertEqual(self.hourly[0]["timestamp"], "2025-08-01T00:00:00+02:00")
        self.assertEqual(self.hourly[-1]["timestamp"], "2025-09-30T23:00:00+02:00")

    def test_05_timestamps_align_exactly_with_frozen_stage2(self) -> None:
        self.assertEqual(
            [row["timestamp"] for row in self.hourly],
            [row["timestamp"] for row in self.stage2],
        )

    def test_06_no_timestamp_is_missing_or_duplicated(self) -> None:
        timestamps = [datetime.fromisoformat(row["timestamp"]) for row in self.hourly]
        self.assertEqual(len(set(timestamps)), 1464)
        self.assertTrue(all(right - left == timedelta(hours=1) for left, right in zip(timestamps, timestamps[1:])))

    def test_07_timezone_conversion_is_explicit_and_correct(self) -> None:
        for row in self.hourly:
            target = datetime.fromisoformat(row["timestamp"])
            source_utc = datetime.fromisoformat(row["pvgis_utc_timestamp"])
            source_local = datetime.fromisoformat(row["pvgis_local_timestamp"])
            self.assertEqual(target.utcoffset(), timedelta(hours=2))
            self.assertEqual(source_utc.utcoffset(), timedelta(0))
            self.assertEqual(source_local.utcoffset(), timedelta(hours=2))
            self.assertEqual(source_local.minute, 10)
            self.assertEqual((target.month, target.day, target.hour), (source_local.month, source_local.day, source_local.hour))
            self.assertIn("UTC converted to Europe/Madrid", row["timezone_treatment"])

    def test_08_source_profile_nighttime_generation_is_exactly_zero(self) -> None:
        night = [row for row in self.hourly if float(row["pvgis_sun_height_degrees"]) <= 0]
        self.assertGreater(len(night), 0)
        self.assertTrue(all(float(row["pv_generation_kwh_per_kwp"]) == 0 for row in night))
        self.assertEqual(self.validation["pvgis_source_night_nonzero_count"], 0)

    def test_09_annual_production_is_positive_and_physically_plausible(self) -> None:
        annual = self.examples["reference_system"]["annual_generation_kwh_per_kwp"]
        self.assertGreater(annual, 500)
        self.assertLess(annual, 2500)
        self.assertEqual(annual, 1559.01)

    def test_10_exactly_twelve_monthly_values_exist(self) -> None:
        self.assertEqual(len(self.monthly), 12)
        self.assertEqual([int(row["month"]) for row in self.monthly], list(range(1, 13)))

    def test_11_monthly_values_sum_to_the_pvgis_annual_value(self) -> None:
        total = sum(float(row["monthly_generation_kwh_per_kwp"]) for row in self.monthly)
        annual = float(self.monthly[0]["annual_generation_kwh_per_kwp"])
        self.assertAlmostEqual(total, annual, places=9)
        self.assertAlmostEqual(
            sum(float(row["monthly_share_of_annual_generation"]) for row in self.monthly), 1.0, places=12
        )

    def test_12_demo_capacities_scale_linearly_from_one_kwp(self) -> None:
        annual = self.examples["reference_system"]["annual_generation_kwh_per_kwp"]
        reference_months = {
            row["month"]: row["generation_kwh_per_kwp"]
            for row in self.examples["reference_system"]["monthly_generation_kwh_per_kwp"]
        }
        self.assertEqual(tuple(row["capacity_kwp"] for row in self.examples["capacity_examples"]), DEMO_CAPACITIES_KWP)
        for example in self.examples["capacity_examples"]:
            capacity = example["capacity_kwp"]
            self.assertAlmostEqual(example["annual_generation_kwh"], annual * capacity, places=9)
            for month in example["monthly_generation_kwh"]:
                self.assertAlmostEqual(
                    month["generation_kwh"], reference_months[month["month"]] * capacity, places=9
                )

    def test_13_arbitrary_positive_capacity_scales_exactly(self) -> None:
        capacity = 4.25
        generation = get_pv_generation(capacity)
        self.assertEqual(len(generation), 1464)
        for source, scaled in zip(self.hourly, generation):
            self.assertEqual(scaled["timestamp"], source["timestamp"])
            self.assertEqual(scaled["capacity_kwp"], capacity)
            self.assertEqual(
                scaled["pv_generation_kwh"],
                float(source["pv_generation_kwh_per_kwp"]) * capacity,
            )
        summary = get_annual_pv_summary(capacity)
        self.assertEqual(summary["annual_generation_kwh"], 1559.01 * capacity)
        self.assertEqual(len(summary["monthly_generation_kwh"]), 12)

    def test_14_invalid_capacity_is_rejected_cleanly(self) -> None:
        for value in (0, -1, None, "5", True, float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    get_pv_generation(value)
                with self.assertRaises(ValueError):
                    get_annual_pv_summary(value)

    def test_15_deterministic_rerun_is_byte_identical(self) -> None:
        paths = [
            HOURLY_OUTPUT,
            MONTHLY_OUTPUT,
            EXAMPLES_OUTPUT,
            VALIDATION_OUTPUT,
            FIGURES_DIR / "pv_monthly_generation.svg",
            FIGURES_DIR / "pv_aug_sep_profile.svg",
        ]
        before = {path: sha256(path) for path in paths}
        run(refresh_pvgis=False)
        first = {path: sha256(path) for path in paths}
        run(refresh_pvgis=False)
        second = {path: sha256(path) for path in paths}
        self.assertEqual(before, first)
        self.assertEqual(first, second)

    def test_16_no_demand_optimization_tariff_or_economics_logic_was_added(self) -> None:
        self.assertFalse(self.examples["optimization_implemented"])
        self.assertFalse(self.examples["economics_implemented"])
        self.assertFalse(self.examples["battery_implemented"])
        forbidden_fields = {
            "load_kwh", "self_consumed_pv", "grid_import", "exported_pv", "tariff_eur_per_kwh",
            "savings", "payback", "optimized_schedule",
        }
        self.assertTrue(forbidden_fields.isdisjoint(self.hourly[0]))
        for path in (ROOT / "src" / "hackowatt_stage8").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = {
                node.module for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module
            }
            self.assertFalse(any(name.startswith("hackowatt_stage3") for name in imported))
            self.assertFalse(any(name.startswith("hackowatt_stage5") for name in imported))
            self.assertFalse(any(name.startswith("hackowatt_stage6") for name in imported))

    def test_17_raw_pvgis_provenance_is_complete(self) -> None:
        self.assertEqual(self.raw["source"], "European Commission Joint Research Centre PVGIS 5.3")
        self.assertEqual(set(self.raw["requests"]), {"PVcalc", "seriescalc"})
        self.assertEqual(self.raw["requests"]["PVcalc"]["parameters"]["peakpower"], 1.0)
        self.assertEqual(self.raw["requests"]["seriescalc"]["parameters"]["startyear"], 2023)
        self.assertEqual(len(self.raw["requests"]["seriescalc"]["response"]["outputs"]["hourly"]), 8760)

    def test_18_stage2_solar_is_only_a_descriptive_sanity_check(self) -> None:
        self.assertGreater(self.validation["stage2_shortwave_vs_pv_correlation_all_hours"], 0)
        self.assertGreater(self.validation["stage2_shortwave_vs_pv_correlation_daylight_hours"], 0)
        self.assertIn("sanity check only", self.validation["stage2_solar_use"])

    def test_19_figures_are_valid_svg(self) -> None:
        for name in ("pv_monthly_generation.svg", "pv_aug_sep_profile.svg"):
            root = ET.parse(FIGURES_DIR / name).getroot()
            self.assertTrue(root.tag.endswith("svg"))


if __name__ == "__main__":
    unittest.main()
