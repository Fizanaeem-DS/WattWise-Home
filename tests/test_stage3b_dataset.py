"""Independent acceptance tests for Stage 3B major-system outputs."""

from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta, timezone
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hackowatt_stage3b.generator import (  # noqa: E402
    NoFeasibleStartError,
    _random_start_outside_away,
    generate,
)


STAGE2 = ROOT / "data" / "processed" / "stage2_barcelona_weather_solar_hourly.csv"
STAGE3A = ROOT / "data" / "processed" / "stage3a_base_routine_hourly.csv"
STAGE3A_LEDGER = ROOT / "data" / "processed" / "stage3a_event_ledger.json"
HOURLY = ROOT / "data" / "processed" / "stage3b_major_systems_hourly.csv"
LEDGER = ROOT / "data" / "processed" / "stage3b_event_ledger.json"
METADATA = ROOT / "data" / "processed" / "stage3b_metadata.json"
VALIDATION = ROOT / "data" / "processed" / "stage3b_validation_report.json"


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def overlap_hours(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> float:
    return max(0.0, (min(a_end, b_end) - max(a_start, b_start)).total_seconds() / 3600)


class SequenceRandom:
    """Minimal deterministic source for directly exercising rejection resampling."""

    def __init__(self, values: list[float]) -> None:
        self.values = iter(values)

    def random(self) -> float:
        return next(self.values)


class Stage3BAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stage2_columns, cls.stage2 = read_csv(STAGE2)
        cls.stage3a_columns, cls.stage3a = read_csv(STAGE3A)
        cls.columns, cls.rows = read_csv(HOURLY)
        cls.timestamps = [datetime.fromisoformat(row["timestamp"]) for row in cls.rows]
        cls.stage3a_ledger = json.loads(STAGE3A_LEDGER.read_text(encoding="utf-8"))
        cls.ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
        cls.metadata = json.loads(METADATA.read_text(encoding="utf-8"))
        cls.validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
        cls.away = [
            (datetime.fromisoformat(item["away_start"]), datetime.fromisoformat(item["away_end"]))
            for item in cls.stage3a_ledger["away_events"]
        ]

    def test_exact_source_timeline_and_stage_boundary(self) -> None:
        self.assertEqual(len(self.rows), 1_464)
        self.assertEqual(
            [row["timestamp"] for row in self.rows],
            [row["timestamp"] for row in self.stage2],
        )
        self.assertEqual(
            [row["timestamp"] for row in self.rows],
            [row["timestamp"] for row in self.stage3a],
        )
        self.assertEqual(self.rows[0]["timestamp"], "2025-08-01T00:00:00+02:00")
        self.assertEqual(self.rows[-1]["timestamp"], "2025-09-30T23:00:00+02:00")
        self.assertEqual(len(self.timestamps), len(set(self.timestamps)))
        utc = [timestamp.astimezone(timezone.utc) for timestamp in self.timestamps]
        self.assertTrue(all(b - a == timedelta(hours=1) for a, b in zip(utc, utc[1:])))
        self.assertTrue(all(ts.utcoffset() == timedelta(hours=2) for ts in self.timestamps))
        self.assertNotIn("stage3a_total_kwh", self.columns)
        self.assertNotIn("refrigerator_kwh", self.columns)

    def test_general_energy_arithmetic_and_validation_report(self) -> None:
        components = (
            "hvac_kwh",
            "ev_total_kwh",
            "pool_circulation_kwh",
            "pool_heating_kwh",
            "sauna_kwh",
        )
        for row in self.rows:
            values = [float(row[name]) for name in components]
            self.assertTrue(all(value >= 0 for value in values))
            self.assertAlmostEqual(float(row["stage3b_total_kwh"]), sum(values), places=8)
            self.assertAlmostEqual(
                float(row["hvac_kwh"]),
                float(row["heating_kwh"]) + float(row["cooling_kwh"]),
                places=8,
            )
            self.assertAlmostEqual(
                float(row["ev_total_kwh"]),
                float(row["ev1_charging_kwh"]) + float(row["ev2_charging_kwh"]),
                places=8,
            )
        self.assertEqual(self.validation["status"], "pass")
        self.assertTrue(all(self.validation["checks"].values()))

    def test_daily_away_classification_uses_exact_2300_rule(self) -> None:
        zone = ZoneInfo("Europe/Madrid")
        for day_text, classification in self.ledger["daily_stage3b_classification"].items():
            day = date.fromisoformat(day_text)
            instant = datetime.combine(day, time(23), tzinfo=zone)
            active = any(start <= instant < end for start, end in self.away)
            expected = "AWAY_DAY" if active else (
                "WE_HOME" if day.weekday() >= 5 else "WD_HOME"
            )
            self.assertEqual(classification, expected)

    def test_hvac_ranges_controller_and_recurrence(self) -> None:
        params = self.metadata["sampled_household_parameters"]
        self.assertTrue(1.5 <= params["heating_power_kw"] <= 4.0)
        self.assertTrue(1.0 <= params["cooling_power_kw"] <= 2.5)
        self.assertTrue(20.0 <= params["heating_preference_c"] <= 22.0)
        self.assertTrue(23.0 <= params["cooling_preference_c"] <= 25.0)
        self.assertEqual(self.rows[0]["hvac_mode"], "off")
        self.assertEqual(float(self.rows[0]["hvac_kwh"]), 0.0)
        self.assertAlmostEqual(
            float(self.rows[0]["indoor_temperature_c"]),
            (
                float(self.rows[0]["effective_heating_target_c"])
                + float(self.rows[0]["effective_cooling_target_c"])
            )
            / 2,
            places=8,
        )
        for index, row in enumerate(self.rows):
            heat = float(row["heating_kwh"])
            cool = float(row["cooling_kwh"])
            self.assertFalse(heat > 0 and cool > 0)
            self.assertEqual(row["hvac_mode"] == "heat", heat > 0)
            self.assertEqual(row["hvac_mode"] == "cool", cool > 0)
            if index == 0:
                continue
            prior = self.rows[index - 1]
            effect = 1.0 if prior["hvac_mode"] == "heat" else (-1.0 if prior["hvac_mode"] == "cool" else 0.0)
            expected = float(prior["indoor_temperature_c"]) + (
                float(prior["outdoor_temperature_c"]) - float(prior["indoor_temperature_c"])
            ) / 6 + effect
            self.assertAlmostEqual(float(row["indoor_temperature_c"]), expected, places=7)

    def test_ev_rules_home_state_and_boundary_accounting(self) -> None:
        trips = self.ledger["ev_trip_events"]
        charges = self.ledger["ev_charging_events"]
        self.assertEqual({trip["ev_id"] for trip in trips}, {"EV1", "EV2"})
        trip_by_id = {trip["trip_id"]: trip for trip in trips}
        charge_by_trip = {event["trip_id"]: event for event in charges}
        for trip in trips:
            self.assertEqual(trip["requires_charge"], trip["trip_id"] in charge_by_trip)
        for event in charges:
            self.assertTrue(trip_by_id[event["trip_id"]]["requires_charge"])
            self.assertEqual(event["charging_power_kw"], 7.4)
            self.assertAlmostEqual(
                event["required_energy_kwh"],
                event["delivered_in_window_kwh"] + event["remaining_energy_kwh"],
                places=8,
            )
            self.assertAlmostEqual(
                event["delivered_in_window_kwh"],
                sum(item["energy_kwh"] for item in event["allocations"]),
                places=8,
            )
            if not event["boundary_truncated"]:
                self.assertAlmostEqual(event["remaining_energy_kwh"], 0.0, places=8)
                self.assertAlmostEqual(event["delivered_in_window_kwh"], event["required_energy_kwh"], places=8)
        for row in self.rows:
            self.assertLessEqual(float(row["ev1_charging_kwh"]), 7.4 + 1e-9)
            self.assertLessEqual(float(row["ev2_charging_kwh"]), 7.4 + 1e-9)
            if float(row["ev1_charging_kwh"]) > 0:
                self.assertEqual(row["ev1_home"], "True")
            if float(row["ev2_charging_kwh"]) > 0:
                self.assertEqual(row["ev2_home"], "True")

    def test_pool_circulation_windows_preserve_runtime_and_energy(self) -> None:
        power = self.metadata["sampled_household_parameters"]["pool_circulation_power_kw"]
        self.assertTrue(0.6 <= power <= 1.2)
        for item in self.ledger["pool_circulation_days"]:
            runtime = item["required_runtime_hours"]
            expected_range = (4.0, 6.0) if item["daily_classification"] == "AWAY_DAY" else (6.0, 10.0)
            self.assertTrue(expected_range[0] <= runtime <= expected_range[1])
            self.assertIn(item["window_count"], {1, 2})
            self.assertEqual(len(item["windows"]), item["window_count"])
            self.assertAlmostEqual(runtime, sum(window["duration_hours"] for window in item["windows"]), places=9)
            # Metadata exposes the once-sampled power rounded to nine decimals,
            # while the event ledger retains full internal precision.
            self.assertAlmostEqual(item["required_energy_kwh"], power * runtime, places=8)
            self.assertAlmostEqual(item["allocated_energy_kwh"], item["required_energy_kwh"], places=8)

    def test_pool_heating_and_sauna_never_overlap_exact_away(self) -> None:
        all_events = self.ledger["pool_heating_events"] + self.ledger["sauna_events"]
        resampled = 0
        for event in all_events:
            start = datetime.fromisoformat(event["start"])
            end = datetime.fromisoformat(event["end"])
            initial = datetime.fromisoformat(event["initial_sampled_start"])
            self.assertTrue(all(overlap_hours(start, end, a_start, a_end) == 0 for a_start, a_end in self.away))
            self.assertAlmostEqual((end - start).total_seconds() / 3600, event["duration_hours"], places=9)
            self.assertAlmostEqual(event["required_energy_kwh"], event["power_kw"] * event["duration_hours"], places=9)
            self.assertAlmostEqual(event["allocated_energy_kwh"], event["required_energy_kwh"], places=8)
            if event["start_resampled_due_to_away"]:
                resampled += 1
                initial_end = initial + timedelta(hours=event["duration_hours"])
                self.assertTrue(any(overlap_hours(initial, initial_end, a_start, a_end) > 0 for a_start, a_end in self.away))
        self.assertGreater(resampled, 0, "the fixed seed must exercise at least one overlap resampling")

    def test_forced_overlap_resamples_start_only_for_both_systems(self) -> None:
        zone = ZoneInfo("Europe/Madrid")
        day = date(2025, 8, 10)
        cases = (
            ("pool heating", 8.0, 14.0, 2.0, [0.40, 0.00], 4.2, 10, 12),
            ("sauna", 19.0, 22.0, 1.5, [0.40, 2 / 3], 7.5, 20, 21),
        )
        for system, lower, upper, duration, draws, power, away_start_hour, away_end_hour in cases:
            with self.subTest(system=system):
                away = [{
                    "start": datetime(2025, 8, 10, away_start_hour, tzinfo=zone),
                    "end": datetime(2025, 8, 10, away_end_hour, tzinfo=zone),
                }]
                start, initial, changed, attempts = _random_start_outside_away(
                    SequenceRandom(draws), day, lower, upper, duration, away, system
                )
                end = start + timedelta(hours=duration)
                self.assertTrue(changed)
                self.assertEqual(attempts, 1)
                self.assertNotEqual(start, initial)
                self.assertEqual((end - start).total_seconds() / 3600, duration)
                self.assertEqual(power * ((end - start).total_seconds() / 3600), power * duration)
                self.assertEqual(overlap_hours(start, end, away[0]["start"], away[0]["end"]), 0)

    def test_no_feasible_overlap_case_stops(self) -> None:
        zone = ZoneInfo("Europe/Madrid")
        day = date(2025, 8, 10)
        away = [{
            "start": datetime(2025, 8, 10, 7, tzinfo=zone),
            "end": datetime(2025, 8, 10, 17, tzinfo=zone),
        }]
        with self.assertRaisesRegex(NoFeasibleStartError, "no complete event fits"):
            _random_start_outside_away(
                SequenceRandom([0.5]), day, 8.0, 14.0, 2.0, away, "pool heating"
            )

    def test_single_boundary_start_is_used_when_it_is_the_only_feasible_start(self) -> None:
        zone = ZoneInfo("Europe/Madrid")
        day = date(2025, 8, 10)
        away = [
            {
                "start": datetime(2025, 8, 10, 7, tzinfo=zone),
                "end": datetime(2025, 8, 10, 10, tzinfo=zone),
            },
            {
                "start": datetime(2025, 8, 10, 12, tzinfo=zone),
                "end": datetime(2025, 8, 10, 16, tzinfo=zone),
            },
        ]
        start, initial, changed, attempts = _random_start_outside_away(
            SequenceRandom([0.5]), day, 8.0, 14.0, 2.0, away, "pool heating"
        )
        self.assertEqual(start, datetime(2025, 8, 10, 10, tzinfo=zone))
        self.assertNotEqual(start, initial)
        self.assertTrue(changed)
        self.assertEqual(attempts, 1)

    def test_fixed_seed_reproduces_all_stage3b_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            generated_hourly = temp / "hourly.csv"
            generated_ledger = temp / "ledger.json"
            generated_metadata = temp / "metadata.json"
            generate(
                hourly_output=generated_hourly,
                ledger_output=generated_ledger,
                metadata_output=generated_metadata,
            )
            self.assertEqual(generated_hourly.read_bytes(), HOURLY.read_bytes())
            self.assertEqual(generated_ledger.read_bytes(), LEDGER.read_bytes())
            self.assertEqual(generated_metadata.read_bytes(), METADATA.read_bytes())


if __name__ == "__main__":
    unittest.main()
