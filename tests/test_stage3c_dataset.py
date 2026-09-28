"""Independent acceptance tests for the Stage 3C deterministic integration."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hackowatt_stage3c.config import (  # noqa: E402
    SOURCE_PATHS,
    STAGE3A_COMPONENT_COLUMNS,
    STAGE3B_COMPONENT_COLUMNS,
    WEATHER_COLUMNS,
)
from hackowatt_stage3c.generator import generate  # noqa: E402


STAGE2 = ROOT / "data" / "processed" / "stage2_barcelona_weather_solar_hourly.csv"
STAGE3A = ROOT / "data" / "processed" / "stage3a_base_routine_hourly.csv"
STAGE3B = ROOT / "data" / "processed" / "stage3b_major_systems_hourly.csv"
STAGE3B_LEDGER = ROOT / "data" / "processed" / "stage3b_event_ledger.json"
HOURLY = ROOT / "data" / "processed" / "stage3c_household_hourly.csv"
METADATA = ROOT / "data" / "processed" / "stage3c_metadata.json"
VALIDATION = ROOT / "data" / "processed" / "stage3c_validation_report.json"


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Stage3CAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stage2_columns, cls.stage2 = read_csv(STAGE2)
        cls.stage3a_columns, cls.stage3a = read_csv(STAGE3A)
        cls.stage3b_columns, cls.stage3b = read_csv(STAGE3B)
        cls.columns, cls.rows = read_csv(HOURLY)
        cls.metadata = json.loads(METADATA.read_text(encoding="utf-8"))
        cls.validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
        cls.stage3b_ledger = json.loads(STAGE3B_LEDGER.read_text(encoding="utf-8"))

    def test_exact_one_to_one_timeline_join(self) -> None:
        output_timestamps = [row["timestamp"] for row in self.rows]
        self.assertEqual(len(output_timestamps), 1_464)
        self.assertEqual(output_timestamps, [row["timestamp"] for row in self.stage2])
        self.assertEqual(output_timestamps, [row["timestamp"] for row in self.stage3a])
        self.assertEqual(output_timestamps, [row["timestamp"] for row in self.stage3b])
        self.assertEqual(output_timestamps[0], "2025-08-01T00:00:00+02:00")
        self.assertEqual(output_timestamps[-1], "2025-09-30T23:00:00+02:00")
        parsed = [datetime.fromisoformat(value) for value in output_timestamps]
        self.assertEqual(len(parsed), len(set(parsed)))
        utc = [value.astimezone(timezone.utc) for value in parsed]
        self.assertTrue(all(b - a == timedelta(hours=1) for a, b in zip(utc, utc[1:])))
        self.assertTrue(all(value.utcoffset() == timedelta(hours=2) for value in parsed))

    def test_frozen_stage3a_components_are_preserved_text_exactly(self) -> None:
        for output, source in zip(self.rows, self.stage3a):
            for column in (*STAGE3A_COMPONENT_COLUMNS, "stage3a_total_kwh"):
                self.assertEqual(output[column], source[column], f"{column} at {output['timestamp']}")

    def test_frozen_stage3b_components_are_preserved_text_exactly(self) -> None:
        for output, source in zip(self.rows, self.stage3b):
            for column in (*STAGE3B_COMPONENT_COLUMNS, "stage3b_total_kwh"):
                self.assertEqual(output[column], source[column], f"{column} at {output['timestamp']}")

    def test_weather_and_context_are_preserved_without_contradictory_duplicates(self) -> None:
        self.assertNotIn("outdoor_temperature_c", self.columns)
        for output, weather, stage3a, stage3b in zip(self.rows, self.stage2, self.stage3a, self.stage3b):
            for column in WEATHER_COLUMNS:
                self.assertEqual(output[column], weather[column])
            for column in (
                "day_type",
                "is_weekend",
                "daytime_occupancy_state",
                "occupancy_state",
                "away",
                "guest_event",
            ):
                self.assertEqual(output[column], stage3a[column])
            for column in (
                "indoor_temperature_c",
                "effective_heating_target_c",
                "effective_cooling_target_c",
                "hvac_mode",
                "ev1_home",
                "ev2_home",
            ):
                self.assertEqual(output[column], stage3b[column])

    def test_household_total_is_exact_sum_of_frozen_stage_totals(self) -> None:
        for output, stage3a, stage3b in zip(self.rows, self.stage3a, self.stage3b):
            self.assertEqual(
                Decimal(output["household_total_kwh"]),
                Decimal(stage3a["stage3a_total_kwh"]) + Decimal(stage3b["stage3b_total_kwh"]),
            )
        expected_total = sum(
            (
                Decimal(a["stage3a_total_kwh"]) + Decimal(b["stage3b_total_kwh"])
                for a, b in zip(self.stage3a, self.stage3b)
            ),
            Decimal(0),
        )
        self.assertEqual(
            sum((Decimal(row["household_total_kwh"]) for row in self.rows), Decimal(0)),
            expected_total,
        )

    def test_categories_reconcile_from_existing_components(self) -> None:
        energy_columns = (
            *STAGE3A_COMPONENT_COLUMNS,
            *STAGE3B_COMPONENT_COLUMNS,
            "stage3a_total_kwh",
            "stage3b_total_kwh",
            "base_fixed_kwh",
            "routine_behavior_kwh",
            "ev_kwh",
            "pool_kwh",
            "household_total_kwh",
        )
        for row in self.rows:
            self.assertTrue(all(Decimal(row[column]) >= 0 for column in energy_columns))
            self.assertEqual(
                Decimal(row["base_fixed_kwh"]),
                Decimal(row["refrigerator_kwh"]) + Decimal(row["smart_home_base_kwh"]),
            )
            self.assertEqual(
                Decimal(row["routine_behavior_kwh"]),
                sum((Decimal(row[column]) for column in STAGE3A_COMPONENT_COLUMNS[2:]), Decimal(0)),
            )
            self.assertEqual(Decimal(row["ev_kwh"]), Decimal(row["ev_total_kwh"]))
            self.assertEqual(
                Decimal(row["pool_kwh"]),
                Decimal(row["pool_circulation_kwh"]) + Decimal(row["pool_heating_kwh"]),
            )
            categories = sum(
                (
                    Decimal(row[column])
                    for column in (
                        "base_fixed_kwh",
                        "routine_behavior_kwh",
                        "hvac_kwh",
                        "ev_kwh",
                        "pool_kwh",
                        "sauna_kwh",
                    )
                ),
                Decimal(0),
            )
            self.assertLessEqual(abs(Decimal(row["household_total_kwh"]) - categories), Decimal("1e-9"))

    def test_metadata_diagnostics_recompute_from_hourly_profile(self) -> None:
        values = [Decimal(row["household_total_kwh"]) for row in self.rows]
        diagnostics = self.metadata["hourly_diagnostics_kwh"]
        self.assertAlmostEqual(diagnostics["mean"], float(statistics.mean(values)), places=9)
        self.assertAlmostEqual(diagnostics["median"], float(statistics.median(values)), places=9)
        self.assertAlmostEqual(
            diagnostics["population_standard_deviation"], float(statistics.pstdev(values)), places=9
        )
        self.assertAlmostEqual(diagnostics["minimum"], float(min(values)), places=9)
        self.assertAlmostEqual(diagnostics["maximum"], float(max(values)), places=9)
        max_index = max(range(len(values)), key=lambda index: values[index])
        self.assertEqual(diagnostics["maximum_timestamp"], self.rows[max_index]["timestamp"])
        expected_top = sorted(
            self.rows,
            key=lambda row: (-Decimal(row["household_total_kwh"]), row["timestamp"]),
        )[:10]
        self.assertEqual(
            [item["timestamp"] for item in self.metadata["top_10_highest_demand_hours"]],
            [row["timestamp"] for row in expected_top],
        )

    def test_metadata_totals_and_category_shares_reconcile(self) -> None:
        totals = self.metadata["energy_totals_kwh"]
        self.assertAlmostEqual(
            totals["stage3a"], sum(float(row["stage3a_total_kwh"]) for row in self.rows), places=8
        )
        self.assertAlmostEqual(
            totals["stage3b"], sum(float(row["stage3b_total_kwh"]) for row in self.rows), places=8
        )
        self.assertAlmostEqual(
            totals["household"], sum(float(row["household_total_kwh"]) for row in self.rows), places=8
        )
        self.assertAlmostEqual(sum(self.metadata["category_percentage_shares"].values()), 100.0, places=7)

    def test_ev_post_boundary_requirement_is_documented_not_inserted(self) -> None:
        truncated = [
            event for event in self.stage3b_ledger["ev_charging_events"]
            if event["boundary_truncated"]
        ]
        expected_remaining = sum(event["remaining_energy_kwh"] for event in truncated)
        boundary = self.metadata["ev_post_boundary_accounting"]
        self.assertEqual(boundary["boundary_truncated_event_count"], len(truncated))
        self.assertAlmostEqual(boundary["remaining_energy_outside_profile_kwh"], expected_remaining, places=9)
        self.assertFalse(boundary["included_in_hourly_profile"])
        self.assertEqual(len(self.rows), 1_464)
        self.assertAlmostEqual(
            self.metadata["energy_totals_kwh"]["household"],
            self.metadata["energy_totals_kwh"]["stage3a"]
            + self.metadata["energy_totals_kwh"]["stage3b"],
            places=8,
        )

    def test_source_fingerprints_and_no_new_behavioral_assumptions(self) -> None:
        self.assertEqual(self.metadata["behavioral_assumptions_added"], [])
        for name, path in SOURCE_PATHS.items():
            self.assertEqual(self.metadata["source_sha256"][name], sha256(path))
        self.assertEqual(self.validation["status"], "pass")
        self.assertTrue(all(self.validation["checks"].values()))

    def test_deterministic_generation_and_source_immutability(self) -> None:
        before = {name: sha256(path) for name, path in SOURCE_PATHS.items()}
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            generated_hourly = temp / "hourly.csv"
            generated_metadata = temp / "metadata.json"
            generate(hourly_output=generated_hourly, metadata_output=generated_metadata)
            self.assertEqual(generated_hourly.read_bytes(), HOURLY.read_bytes())
            self.assertEqual(generated_metadata.read_bytes(), METADATA.read_bytes())
        after = {name: sha256(path) for name, path in SOURCE_PATHS.items()}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
