"""Independent acceptance tests for Stage 3A outputs."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hackowatt_stage3a.config import COMPONENT_COLUMNS, MAJOR_SYSTEM_NAMES  # noqa: E402
from hackowatt_stage3a.generator import generate  # noqa: E402


STAGE2 = ROOT / "data" / "processed" / "stage2_barcelona_weather_solar_hourly.csv"
HOURLY = ROOT / "data" / "processed" / "stage3a_base_routine_hourly.csv"
LEDGER = ROOT / "data" / "processed" / "stage3a_event_ledger.json"
METADATA = ROOT / "data" / "processed" / "stage3a_metadata.json"
VALIDATION = ROOT / "data" / "processed" / "stage3a_validation_report.json"


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


class Stage3AAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_columns, cls.source = read_csv(STAGE2)
        cls.columns, cls.rows = read_csv(HOURLY)
        cls.timestamps = [datetime.fromisoformat(row["timestamp"]) for row in cls.rows]
        cls.ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
        cls.metadata = json.loads(METADATA.read_text(encoding="utf-8"))
        cls.validation = json.loads(VALIDATION.read_text(encoding="utf-8"))

    def test_exact_source_timeline_is_preserved(self) -> None:
        self.assertEqual(len(self.rows), 1_464)
        self.assertEqual(
            [row["timestamp"] for row in self.rows],
            [row["timestamp"] for row in self.source],
        )
        self.assertEqual(self.rows[0]["timestamp"], "2025-08-01T00:00:00+02:00")
        self.assertEqual(self.rows[-1]["timestamp"], "2025-09-30T23:00:00+02:00")
        self.assertEqual(len(self.timestamps), len(set(self.timestamps)))
        utc = [timestamp.astimezone(timezone.utc) for timestamp in self.timestamps]
        self.assertTrue(all(b - a == timedelta(hours=1) for a, b in zip(utc, utc[1:])))
        self.assertTrue(all(ts.utcoffset() == timedelta(hours=2) for ts in self.timestamps))

    def test_components_are_nonnegative_and_total_is_exact_sum(self) -> None:
        for row in self.rows:
            components = [float(row[name]) for name in COMPONENT_COLUMNS]
            self.assertTrue(all(value >= 0 for value in components))
            self.assertAlmostEqual(float(row["stage3a_total_kwh"]), sum(components), places=8)

    def test_household_parameters_are_sampled_once_inside_official_ranges(self) -> None:
        params = self.metadata["sampled_household_parameters"]
        ranges = {
            "refrigerator_daily_kwh": (1.5, 2.2),
            "smart_home_base_kw": (0.05, 0.15),
            "oven_kw": (2.0, 2.5),
            "hob_kw": (1.5, 4.0),
            "tv_kw": (0.10, 0.20),
            "computer_kw": (0.05, 0.25),
            "installed_lighting_kw": (0.10, 0.40),
        }
        for name, (lower, upper) in ranges.items():
            self.assertLessEqual(lower, params[name], name)
            self.assertLessEqual(params[name], upper, name)
        base_values = {float(row["smart_home_base_kwh"]) for row in self.rows}
        self.assertEqual(len(base_values), 1)

    def test_away_suppression_and_fixed_load_continuity(self) -> None:
        suppressed = (
            "cooking_kwh",
            "dishwasher_kwh",
            "washer_kwh",
            "dryer_kwh",
            "electronics_kwh",
            "phone_tablet_kwh",
            "interior_lighting_kwh",
        )
        away_rows = [row for row in self.rows if row["away"] == "True"]
        self.assertGreater(len(away_rows), 0)
        for row in away_rows:
            self.assertEqual(row["day_type"], "AWAY")
            self.assertEqual(row["occupancy_state"], "EMPTY")
            self.assertTrue(all(float(row[name]) == 0 for name in suppressed))
            self.assertGreater(float(row["refrigerator_kwh"]), 0)
            self.assertGreater(float(row["smart_home_base_kwh"]), 0)

    def test_away_events_are_nonoverlapping_and_preserve_exact_fields(self) -> None:
        previous_end = None
        for event in self.ledger["away_events"]:
            self.assertIn("away_start", event)
            self.assertIn("away_end", event)
            self.assertIn("away_duration", event)
            self.assertIn("away_duration_hours", event)
            start = datetime.fromisoformat(event["away_start"])
            end = datetime.fromisoformat(event["away_end"])
            if previous_end is not None:
                self.assertLessEqual(previous_end, start)
            self.assertAlmostEqual(
                event["away_duration_hours"], (end - start).total_seconds() / 3600
            )
            self.assertEqual(event["away_duration"], event["away_duration_hours"])
            previous_end = end

    def test_guest_events_are_coherent_and_never_overlap_away(self) -> None:
        away = [
            (datetime.fromisoformat(item["away_start"]), datetime.fromisoformat(item["away_end"]))
            for item in self.ledger["away_events"]
        ]
        for event in self.ledger["guest_events"]:
            start = datetime.fromisoformat(event["start"])
            end = datetime.fromisoformat(event["end"])
            self.assertIn(event["base_day_type"], {"WD_HOME", "WE_HOME"})
            self.assertGreaterEqual(start.time(), time(18, 0))
            self.assertLessEqual(start.time(), time(20, 30))
            self.assertLessEqual(end.time(), time(23, 30))
            self.assertGreater(end, start)
            self.assertTrue(all(end <= a_start or start >= a_end for a_start, a_end in away))

    def test_occupancy_midpoint_representation_reconstructs_exactly(self) -> None:
        schedules = {item["date"]: item for item in self.ledger["daily_states"]}
        away = [
            (
                item["event_id"],
                datetime.fromisoformat(item["away_start"]),
                datetime.fromisoformat(item["away_end"]),
            )
            for item in self.ledger["away_events"]
        ]
        for row, timestamp in zip(self.rows, self.timestamps):
            midpoint = timestamp + timedelta(minutes=30)
            active_away = next(
                (event_id for event_id, start, end in away if start <= midpoint < end), None
            )
            schedule = schedules[timestamp.date().isoformat()]
            if active_away:
                expected = "EMPTY"
                self.assertEqual(row["away_event_id"], active_away)
            elif schedule["daytime_occupancy_state"] == "FULL":
                expected = "FULL"
            else:
                departure = datetime.fromisoformat(schedule["household_departure"])
                returned = datetime.fromisoformat(schedule["household_return"])
                expected = (
                    schedule["daytime_occupancy_state"]
                    if departure <= midpoint < returned
                    else "FULL"
                )
            self.assertEqual(row["occupancy_state"], expected)

    def test_occupancy_schedules_follow_frozen_ranges(self) -> None:
        for schedule in self.ledger["daily_states"]:
            state = schedule["daytime_occupancy_state"]
            self.assertIn(state, {"EMPTY", "PARTIAL", "FULL"})
            if state == "FULL":
                self.assertIsNone(schedule["household_departure"])
                self.assertIsNone(schedule["household_return"])
                continue
            departure = datetime.fromisoformat(schedule["household_departure"])
            returned = datetime.fromisoformat(schedule["household_return"])
            self.assertLess(departure, returned)
            if schedule["is_weekend"]:
                self.assertTrue(time(10) <= departure.time() <= time(13))
                lower = time(16) if state == "EMPTY" else time(15)
                self.assertTrue(lower <= returned.time() <= time(19))
            else:
                self.assertTrue(time(8, 30) <= departure.time() <= time(9))
                self.assertTrue(time(16) <= returned.time() <= time(19))

    def test_cycle_ranges_dependencies_and_fractional_energy_preservation(self) -> None:
        events = self.ledger["appliance_events"]
        by_id = {event["event_id"]: event for event in events}
        found_fractional = False
        for event in events:
            allocated = sum(item["energy_kwh"] for item in event["allocations"])
            self.assertTrue(
                math.isclose(allocated, event["sampled_energy_kwh"], abs_tol=1e-9)
            )
            if len(event["allocations"]) > 1:
                found_fractional = True
            if event["event_type"] == "dishwasher":
                self.assertTrue(0.8 <= event["sampled_energy_kwh"] <= 1.2)
            elif event["event_type"] == "washer":
                self.assertTrue(0.6 <= event["sampled_energy_kwh"] <= 1.0)
            elif event["event_type"] == "dryer":
                self.assertTrue(1.5 <= event["sampled_energy_kwh"] <= 2.5)
                washer = by_id[event["depends_on_event_id"]]
                self.assertEqual(washer["event_type"], "washer")
                self.assertGreaterEqual(
                    datetime.fromisoformat(event["start"]),
                    datetime.fromisoformat(washer["end"]),
                )
        self.assertTrue(found_fractional)

    def test_event_component_totals_match_hourly_dataset(self) -> None:
        event_components = {
            "cooking_kwh",
            "dishwasher_kwh",
            "washer_kwh",
            "dryer_kwh",
            "electronics_kwh",
            "phone_tablet_kwh",
        }
        event_totals = defaultdict(float)
        for event in self.ledger["appliance_events"]:
            event_totals[event["component"]] += event["sampled_energy_kwh"]
        for component in event_components:
            hourly_total = sum(float(row[component]) for row in self.rows)
            self.assertAlmostEqual(hourly_total, event_totals[component], places=6)

    def test_refrigerator_daily_energy_is_preserved(self) -> None:
        by_day = defaultdict(float)
        for row, timestamp in zip(self.rows, self.timestamps):
            by_day[timestamp.date()] += float(row["refrigerator_kwh"])
        expected = self.metadata["sampled_household_parameters"]["refrigerator_daily_kwh"]
        self.assertEqual(len(by_day), 61)
        for total in by_day.values():
            self.assertAlmostEqual(total, expected, places=7)

    def test_no_stage3b_major_system_load_exists(self) -> None:
        for column in self.columns:
            self.assertFalse(any(name in column.lower() for name in MAJOR_SYSTEM_NAMES), column)
        self.assertTrue(self.validation["checks"]["no_stage3b_major_system_columns"])

    def test_fixed_seed_reproduces_hourly_and_event_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            generated_hourly = temp / "hourly.csv"
            generated_ledger = temp / "ledger.json"
            generated_metadata = temp / "metadata.json"
            generate(
                stage2_path=STAGE2,
                hourly_output=generated_hourly,
                ledger_output=generated_ledger,
                metadata_output=generated_metadata,
            )
            self.assertEqual(generated_hourly.read_bytes(), HOURLY.read_bytes())
            self.assertEqual(generated_ledger.read_bytes(), LEDGER.read_bytes())


if __name__ == "__main__":
    unittest.main()

