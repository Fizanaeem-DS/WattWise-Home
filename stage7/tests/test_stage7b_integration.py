"""Stage 7B production integration and frozen-upstream regression tests."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "stage7" / "backend"))

from constraints.stage7_constraints import get_constraint, get_constraints, validate_constraints  # noqa: E402
from contract.production_schema import ProductionEventConstraint  # noqa: E402
from contract.schema import FlexibilityClass as F, LoadComponent as L  # noqa: E402
from hackowatt_stage7 import build_optimization_requirements  # noqa: E402
from hackowatt_stage7.config import FROZEN_UPSTREAM_FILE_COUNT, FROZEN_UPSTREAM_TREE_SHA256  # noqa: E402
from hackowatt_stage7.validate import frozen_upstream_identity, validate_requirements  # noqa: E402


class Stage7BIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = json.loads((ROOT / "data/processed/stage3a_event_ledger.json").read_text())
        cls.b = json.loads((ROOT / "data/processed/stage3b_event_ledger.json").read_text())
        cls.meta = json.loads((ROOT / "data/processed/stage3b_metadata.json").read_text())
        cls.requirements = build_optimization_requirements()
        cls.events = {event.event_id: event for event in cls.requirements.events}

    def test_01_classification_is_exact(self):
        expected = {
            F.FIXED: {L.FRIDGE_FREEZER, L.SMART_HOME_BASE, L.LIGHTING_EXTERIOR},
            F.BEHAVIOR_DRIVEN: {L.COOKING, L.TV_COMPUTER, L.PHONE_TABLET, L.LIGHTING_INTERIOR},
            F.LIMITED_FLEXIBILITY: {L.HVAC, L.SAUNA, L.POOL_HEATING},
            F.SHIFTABLE: {L.EV1, L.EV2, L.POOL_CIRCULATION, L.DISHWASHER, L.WASHER, L.DRYER},
        }
        actual = {key: {item.component for item in get_constraints() if item.flexibility_class == key} for key in expected}
        self.assertEqual(actual, expected)
        self.assertEqual(validate_constraints(), [])

    def test_02_production_schema_has_requested_fields(self):
        names = {item.name for item in fields(ProductionEventConstraint)}
        self.assertTrue({"event_id", "component", "flexibility_class", "date", "energy_kwh",
                         "duration_hours", "power_kw", "actual_start", "actual_end", "preferred_start",
                         "feasible_start", "feasible_end", "deadline", "availability_intervals",
                         "depends_on_event_id", "vehicle_id", "next_departure", "source", "provenance"} <= names)

    def test_03_every_production_event_has_unique_identity(self):
        ids = [event.event_id for event in self.requirements.events]
        self.assertEqual(len(ids), 177)
        self.assertEqual(len(ids), len(set(ids)))

    def test_04_stage3_energy_is_preserved(self):
        for item in self.a["appliance_events"]:
            if item["event_type"] in {"dishwasher", "washer", "dryer"}:
                self.assertAlmostEqual(self.events[item["event_id"]].energy_kwh, item["sampled_energy_kwh"], places=12)
        for key, ledger_key, id_key, energy_key in (
            ("ev", "ev_charging_events", "charging_event_id", "required_energy_kwh"),
            ("heat", "pool_heating_events", "event_id", "required_energy_kwh"),
            ("sauna", "sauna_events", "event_id", "required_energy_kwh"),
        ):
            for item in self.b[ledger_key]:
                self.assertAlmostEqual(self.events[item[id_key]].energy_kwh, item[energy_key], places=12, msg=key)

    def test_05_stage3_duration_is_preserved(self):
        for item in self.a["appliance_events"]:
            if item["event_type"] in {"dishwasher", "washer", "dryer"}:
                self.assertAlmostEqual(self.events[item["event_id"]].duration_hours, item["duration_hours"], places=12)
        for item in self.b["pool_circulation_days"]:
            self.assertAlmostEqual(self.events[f"pool_circulation_{item['date']}"].duration_hours,
                                   item["required_runtime_hours"], places=12)
        for item in self.b["pool_heating_events"] + self.b["sauna_events"]:
            self.assertAlmostEqual(self.events[item["event_id"]].duration_hours, item["duration_hours"], places=12)

    def test_06_stage3_power_is_preserved_where_available(self):
        for item in self.a["appliance_events"]:
            if item["event_type"] in {"dishwasher", "washer", "dryer"}:
                self.assertAlmostEqual(self.events[item["event_id"]].power_kw, item["average_power_kw"], places=12)
        for item in self.b["ev_charging_events"]:
            self.assertEqual(self.events[item["charging_event_id"]].power_kw, item["charging_power_kw"])
        for item in self.b["pool_heating_events"] + self.b["sauna_events"]:
            self.assertAlmostEqual(self.events[item["event_id"]].power_kw, item["power_kw"], places=12)

    def test_07_static_representatives_do_not_override_events(self):
        dish_static = get_constraint(L.DISHWASHER).required_energy_kwh
        dish_actual = next(item for item in self.a["appliance_events"] if item["event_type"] == "dishwasher")
        self.assertNotEqual(dish_static, dish_actual["sampled_energy_kwh"])
        self.assertEqual(self.events[dish_actual["event_id"]].energy_kwh, dish_actual["sampled_energy_kwh"])
        self.assertNotEqual(get_constraint(L.POOL_CIRCULATION).required_runtime_hours,
                            self.b["pool_circulation_days"][0]["required_runtime_hours"])

    def test_08_ev_identity_home_availability_and_departure_are_preserved(self):
        for item in self.b["ev_charging_events"]:
            event = self.events[item["charging_event_id"]]
            self.assertEqual(event.vehicle_id, item["ev_id"])
            self.assertEqual(event.component, L.EV1 if item["ev_id"] == "EV1" else L.EV2)
            self.assertEqual(event.availability_intervals[0].start, item["return"])
            self.assertEqual(event.availability_intervals[0].end, item["next_departure"])
            self.assertEqual(event.next_departure, item["next_departure"])

    def test_09_ev_energy_power_and_boundary_accounting_are_preserved(self):
        for item in self.b["ev_charging_events"]:
            event = self.events[item["charging_event_id"]]
            self.assertEqual(event.energy_kwh, item["required_energy_kwh"])
            self.assertEqual(event.max_power_kw, 7.4)
            self.assertEqual(event.boundary_truncated, item["boundary_truncated"])
            self.assertEqual(event.delivered_in_window_kwh, item["delivered_in_window_kwh"])
            self.assertEqual(event.remaining_energy_kwh, item["remaining_energy_kwh"])

    def test_10_pool_circulation_exact_runtime_energy_and_power(self):
        power = self.meta["sampled_household_parameters"]["pool_circulation_power_kw"]
        for item in self.b["pool_circulation_days"]:
            event = self.events[f"pool_circulation_{item['date']}"]
            self.assertEqual(event.duration_hours, item["required_runtime_hours"])
            self.assertEqual(event.energy_kwh, item["required_energy_kwh"])
            self.assertEqual(event.power_kw, power)
            self.assertTrue(event.same_calendar_day)
            self.assertTrue(event.deadline.endswith("T23:59:00+02:00"))

    def test_11_away_pool_circulation_uses_actual_requirement(self):
        away_days = [item for item in self.b["pool_circulation_days"] if item["daily_classification"] == "AWAY_DAY"]
        self.assertTrue(away_days)
        for item in away_days:
            event = self.events[f"pool_circulation_{item['date']}"]
            self.assertEqual(event.duration_hours, item["required_runtime_hours"])
            self.assertLessEqual(event.duration_hours, 6.0)

    def test_12_dishwasher_uses_actual_start_and_next_morning_deadline(self):
        for item in self.a["appliance_events"]:
            if item["event_type"] != "dishwasher":
                continue
            event = self.events[item["event_id"]]
            self.assertEqual(event.feasible_start, item["start"])
            deadline = datetime.fromisoformat(event.deadline)
            self.assertEqual((deadline.hour, deadline.minute), (6, 30))
            self.assertEqual(deadline.date(), datetime.fromisoformat(item["start"]).date() + timedelta(days=1))
            self.assertIsNone(get_constraint(L.DISHWASHER).earliest_start)

    def test_13_dishwasher_cycle_is_coherent(self):
        self.assertTrue(all(event.coherent_cycle for event in self.requirements.events if event.component == L.DISHWASHER))

    def test_14_washer_dryer_dependency_is_machine_readable(self):
        for item in self.a["appliance_events"]:
            if item["event_type"] != "dryer":
                continue
            dryer = self.events[item["event_id"]]
            washer = self.events[item["depends_on_event_id"]]
            self.assertEqual(dryer.depends_on_event_id, washer.event_id)
            self.assertGreaterEqual(datetime.fromisoformat(dryer.actual_start), datetime.fromisoformat(washer.actual_end))
            self.assertEqual(dryer.feasible_start, washer.actual_end)

    def test_15_laundry_same_day_23_deadline_and_no_static_earliest(self):
        for event in self.requirements.events:
            if event.component in {L.WASHER, L.DRYER}:
                deadline = datetime.fromisoformat(event.deadline)
                self.assertTrue(event.same_calendar_day)
                self.assertEqual((deadline.hour, deadline.minute), (23, 0))
                self.assertEqual(deadline.date().isoformat(), event.date)
                self.assertTrue(event.coherent_cycle)
        self.assertIsNone(get_constraint(L.WASHER).earliest_start)
        self.assertIsNone(get_constraint(L.DRYER).earliest_start)

    def test_16_sauna_preferred_plus_minus_one_hour_is_machine_readable(self):
        for item in self.b["sauna_events"]:
            event = self.events[item["event_id"]]
            preferred = datetime.fromisoformat(item["start"])
            self.assertEqual(event.preferred_start, item["start"])
            for interval in event.availability_intervals:
                self.assertGreaterEqual(datetime.fromisoformat(interval.start), preferred - timedelta(hours=1))
                self.assertLessEqual(datetime.fromisoformat(interval.end), preferred + timedelta(hours=1))

    def test_17_sauna_latest_start_is_absolute_2230_not_completion(self):
        static = get_constraint(L.SAUNA)
        self.assertEqual(static.latest_start, "22:30")
        self.assertIsNone(static.latest_completion)
        for event in self.requirements.events:
            if event.component == L.SAUNA:
                latest = datetime.fromisoformat(event.latest_start)
                self.assertEqual((latest.hour, latest.minute), (22, 30))
                self.assertIsNone(event.deadline)

    def test_18_sauna_and_pool_heating_start_support_avoids_exact_away(self):
        away = [(datetime.fromisoformat(x["start"]), datetime.fromisoformat(x["end"])) for x in self.a["away_events"]]
        for event in self.requirements.events:
            if event.component not in {L.SAUNA, L.POOL_HEATING}:
                continue
            duration = timedelta(hours=event.duration_hours)
            for support in event.availability_intervals:
                for start in (datetime.fromisoformat(support.start), datetime.fromisoformat(support.end)):
                    self.assertFalse(any(start < end and start + duration > begin for begin, end in away))

    def test_19_pool_heating_uses_approved_rule(self):
        for item in self.b["pool_heating_events"]:
            event = self.events[item["event_id"]]
            self.assertEqual(datetime.fromisoformat(event.feasible_start).hour, 8)
            deadline = datetime.fromisoformat(event.deadline)
            self.assertEqual((deadline.hour, deadline.minute), (22, 0))
            self.assertTrue(event.same_calendar_day)
            self.assertEqual(event.energy_kwh, item["required_energy_kwh"])
            self.assertEqual(event.duration_hours, item["duration_hours"])
            self.assertEqual(event.power_kw, item["power_kw"])

    def test_20_hvac_modes_bounds_and_recurrence_inputs_are_separate(self):
        hvac = self.requirements.hvac
        self.assertEqual(hvac.heating.mode, "heating")
        self.assertEqual(hvac.cooling.mode, "cooling")
        self.assertEqual(hvac.heating.lower_c, max(hvac.heating.sampled_preference_c - 1, 20))
        self.assertEqual(hvac.heating.upper_c, min(hvac.heating.sampled_preference_c + 1, 22))
        self.assertEqual(hvac.cooling.lower_c, max(hvac.cooling.sampled_preference_c - 1, 23))
        self.assertEqual(hvac.cooling.upper_c, min(hvac.cooling.sampled_preference_c + 1, 25))
        self.assertTrue(hvac.mutually_exclusive)
        self.assertTrue(hvac.limited_preconditioning)
        self.assertTrue(hvac.no_occupied_comfort_violation)
        self.assertEqual((hvac.thermal_time_constant_hours, hvac.heating_effect_c_per_hour,
                          hvac.cooling_effect_c_per_hour, hvac.hysteresis_c), (6.0, 1.0, -1.0, 0.5))
        self.assertEqual(len(hvac.hourly_states), 1464)

    def test_21_production_path_has_no_mock_generator(self):
        self.assertFalse(self.requirements.mock_generator_used)
        self.assertEqual(self.requirements.source, "real")
        self.assertTrue(all(event.source == "real" and event.provenance for event in self.requirements.events))

    def test_22_frozen_upstream_is_byte_identical(self):
        self.assertEqual(frozen_upstream_identity(), (FROZEN_UPSTREAM_FILE_COUNT, FROZEN_UPSTREAM_TREE_SHA256))
        self.assertEqual(validate_requirements(self.requirements)["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
