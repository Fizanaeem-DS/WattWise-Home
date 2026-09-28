"""Programmatic validation for Stage 3B major systems."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Any

from .config import (
    EVENT_LEDGER_OUTPUT,
    HOURLY_OUTPUT,
    METADATA_OUTPUT,
    STAGE2_INPUT,
    STAGE3A_INPUT,
    STAGE3A_LEDGER,
    VALIDATION_OUTPUT,
)


def _read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _overlap_hours(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> float:
    return max(0.0, (min(a_end, b_end) - max(a_start, b_start)).total_seconds() / 3600)


def validate(
    stage2_path: Path = STAGE2_INPUT,
    stage3a_path: Path = STAGE3A_INPUT,
    hourly_path: Path = HOURLY_OUTPUT,
    ledger_path: Path = EVENT_LEDGER_OUTPUT,
    metadata_path: Path = METADATA_OUTPUT,
    report_path: Path = VALIDATION_OUTPUT,
) -> dict[str, Any]:
    _, source = _read(stage2_path)
    _, stage3a = _read(stage3a_path)
    columns, rows = _read(hourly_path)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    timestamps = [datetime.fromisoformat(row["timestamp"]) for row in rows]
    utc = [timestamp.astimezone(timezone.utc) for timestamp in timestamps]

    params = metadata["sampled_household_parameters"]
    parameter_checks = {
        "heating_power": 1.5 <= params["heating_power_kw"] <= 4.0,
        "cooling_power": 1.0 <= params["cooling_power_kw"] <= 2.5,
        "heating_preference": 20.0 <= params["heating_preference_c"] <= 22.0,
        "cooling_preference": 23.0 <= params["cooling_preference_c"] <= 25.0,
        "pool_circulation_power": 0.6 <= params["pool_circulation_power_kw"] <= 1.2,
        "pool_heating_power": 2.0 <= params["pool_heating_power_kw"] <= 5.0,
        "sauna_power": 6.0 <= params["sauna_power_kw"] <= 9.0,
    }

    general_nonnegative = all(
        float(row[column]) >= 0
        for row in rows
        for column in (
            "heating_kwh",
            "cooling_kwh",
            "hvac_kwh",
            "ev1_charging_kwh",
            "ev2_charging_kwh",
            "ev_total_kwh",
            "pool_circulation_kwh",
            "pool_heating_kwh",
            "sauna_kwh",
            "stage3b_total_kwh",
        )
    )
    totals_match = all(
        math.isclose(
            float(row["stage3b_total_kwh"]),
            float(row["hvac_kwh"])
            + float(row["ev_total_kwh"])
            + float(row["pool_circulation_kwh"])
            + float(row["pool_heating_kwh"])
            + float(row["sauna_kwh"]),
            abs_tol=3e-9,
        )
        and math.isclose(
            float(row["hvac_kwh"]),
            float(row["heating_kwh"]) + float(row["cooling_kwh"]),
            abs_tol=2e-9,
        )
        and math.isclose(
            float(row["ev_total_kwh"]),
            float(row["ev1_charging_kwh"]) + float(row["ev2_charging_kwh"]),
            abs_tol=2e-9,
        )
        for row in rows
    )

    # HVAC controller, target, and recurrence checks.
    targets_valid = True
    for row, state in zip(rows, stage3a):
        day_targets = ledger["hvac_daily_targets"][row["timestamp"][:10]]
        normal_heat = day_targets["normal_heating_target_c"]
        normal_cool = day_targets["normal_cooling_target_c"]
        if state["away"] == "True":
            expected_heat, expected_cool = normal_heat - 3, normal_cool + 3
        elif state["occupancy_state"] == "EMPTY":
            expected_heat, expected_cool = normal_heat - 1, normal_cool + 1
        else:
            expected_heat, expected_cool = normal_heat, normal_cool
        targets_valid &= math.isclose(float(row["effective_heating_target_c"]), expected_heat, abs_tol=1e-8)
        targets_valid &= math.isclose(float(row["effective_cooling_target_c"]), expected_cool, abs_tol=1e-8)

    recurrence_valid = True
    controller_valid = rows[0]["hvac_mode"] == "off"
    mutually_exclusive = True
    for index, row in enumerate(rows):
        mode = row["hvac_mode"]
        heat = float(row["heating_kwh"])
        cool = float(row["cooling_kwh"])
        mutually_exclusive &= not (heat > 0 and cool > 0)
        mutually_exclusive &= (mode == "heat") == (heat > 0)
        mutually_exclusive &= (mode == "cool") == (cool > 0)
        if index > 0:
            indoor = float(row["indoor_temperature_c"])
            heat_target = float(row["effective_heating_target_c"])
            cool_target = float(row["effective_cooling_target_c"])
            previous = rows[index - 1]["hvac_mode"]
            if previous == "cool":
                expected_mode = "off" if indoor <= cool_target else "cool"
            elif previous == "heat":
                expected_mode = "off" if indoor >= heat_target else "heat"
            elif indoor > cool_target + 0.5:
                expected_mode = "cool"
            elif indoor < heat_target - 0.5:
                expected_mode = "heat"
            else:
                expected_mode = "off"
            controller_valid &= mode == expected_mode
            prior = rows[index - 1]
            prior_indoor = float(prior["indoor_temperature_c"])
            prior_outdoor = float(prior["outdoor_temperature_c"])
            effect = 1.0 if prior["hvac_mode"] == "heat" else (-1.0 if prior["hvac_mode"] == "cool" else 0.0)
            expected_indoor = prior_indoor + (prior_outdoor - prior_indoor) / 6 + effect
            recurrence_valid &= math.isclose(indoor, expected_indoor, abs_tol=2e-8)
    first_heat = float(rows[0]["effective_heating_target_c"])
    first_cool = float(rows[0]["effective_cooling_target_c"])
    initialization_valid = (
        rows[0]["hvac_mode"] == "off"
        and float(rows[0]["hvac_kwh"]) == 0
        and math.isclose(
            float(rows[0]["indoor_temperature_c"]),
            (first_heat + first_cool) / 2,
            abs_tol=2e-9,
        )
    )

    # EV exact-interval and energy-accounting checks.
    trips = ledger["ev_trip_events"]
    charges = ledger["ev_charging_events"]
    ev_ids_valid = {trip["ev_id"] for trip in trips} <= {"EV1", "EV2"} and {
        charge["ev_id"] for charge in charges
    } <= {"EV1", "EV2"}
    ordinary_probability_valid = all(
        (not trial["eligible"])
        or math.isclose(
            trial["final_leave_probability"],
            min(1.0, trial["base_leave_probability"] * trial["occupancy_modifier"]),
            abs_tol=1e-12,
        )
        for trial in ledger["ordinary_ev_trials"]
    )
    charging_energy_valid = all(
        math.isclose(
            event["required_energy_kwh"],
            event["delivered_in_window_kwh"] + event["remaining_energy_kwh"],
            abs_tol=1e-8,
        )
        and (
            event["boundary_truncated"]
            or (
                math.isclose(event["required_energy_kwh"], event["delivered_in_window_kwh"], abs_tol=1e-8)
                and math.isclose(event["remaining_energy_kwh"], 0.0, abs_tol=1e-8)
            )
        )
        and math.isclose(
            event["delivered_in_window_kwh"],
            sum(item["energy_kwh"] for item in event["allocations"]),
            abs_tol=1e-8,
        )
        for event in charges
    )
    charging_cap_valid = all(
        all(0 <= allocation["energy_kwh"] <= 7.4 + 1e-10 for allocation in event["allocations"])
        for event in charges
    )
    charging_home_valid = True
    charging_before_departure = True
    for event in charges:
        start = datetime.fromisoformat(event["charging_start"])
        end = datetime.fromisoformat(event["charging_end"])
        for trip in trips:
            if trip["ev_id"] != event["ev_id"]:
                continue
            trip_start = datetime.fromisoformat(trip["departure"])
            trip_end = datetime.fromisoformat(trip["return"])
            charging_home_valid &= _overlap_hours(start, end, trip_start, trip_end) == 0
        if event["next_departure"] is not None:
            charging_before_departure &= end <= datetime.fromisoformat(event["next_departure"])
    stage3a_away_events = json.loads(STAGE3A_LEDGER.read_text(encoding="utf-8"))["away_events"]
    away_touched_dates: set[str] = set()
    for away in stage3a_away_events:
        away_start = datetime.fromisoformat(away["start"])
        away_end = datetime.fromisoformat(away["end"])
        cursor = away_start.date()
        last = (away_end - timedelta(microseconds=1)).date()
        while cursor <= last:
            away_touched_dates.add(cursor.isoformat())
            cursor += timedelta(days=1)
    away_mutual_exclusion = all(
        trial["date"] not in away_touched_dates or not trial["eligible"]
        for trial in ledger["ordinary_ev_trials"]
    )

    # Pool circulation window, runtime, and energy checks.
    circulation_valid = True
    for item in ledger["pool_circulation_days"]:
        runtime = item["required_runtime_hours"]
        if item["daily_classification"] == "AWAY_DAY":
            circulation_valid &= 4.0 <= runtime <= 6.0
        else:
            circulation_valid &= 6.0 <= runtime <= 10.0
        circulation_valid &= item["window_count"] in {1, 2}
        circulation_valid &= len(item["windows"]) == item["window_count"]
        circulation_valid &= math.isclose(
            runtime,
            sum(window["duration_hours"] for window in item["windows"]),
            abs_tol=1e-9,
        )
        circulation_valid &= math.isclose(
            item["required_energy_kwh"], item["allocated_energy_kwh"], abs_tol=1e-8
        )
        day = datetime.fromisoformat(item["date"] + "T00:00:00+02:00")
        if item["window_count"] == 1:
            start = datetime.fromisoformat(item["windows"][0]["start"])
            circulation_valid &= day + timedelta(hours=8) <= start <= day + timedelta(hours=12)
        else:
            first_start = datetime.fromisoformat(item["windows"][0]["start"])
            second_start = datetime.fromisoformat(item["windows"][1]["start"])
            circulation_valid &= day + timedelta(hours=6) <= first_start <= day + timedelta(hours=9)
            circulation_valid &= day + timedelta(hours=15) <= second_start <= day + timedelta(hours=18)
            circulation_valid &= 0.50 <= item["first_window_fraction"] <= 0.70
        for first, second in zip(item["windows"], item["windows"][1:]):
            circulation_valid &= datetime.fromisoformat(first["end"]) <= datetime.fromisoformat(second["start"])

    # Pool heating and sauna probabilities, ranges, AWAY exclusion, overlap, energy.
    away_intervals = [
        (datetime.fromisoformat(item["start"]), datetime.fromisoformat(item["end"]))
        for item in stage3a_away_events
    ]
    pool_probability_valid = True
    for item in ledger["pool_heating_daily_activation"]:
        temp = item["daily_mean_outdoor_temperature_c"]
        expected_base = 0.70 if temp < 15 else (0.35 if temp <= 20 else 0.08)
        expected_final = (
            0.0
            if item["daily_classification"] == "AWAY_DAY"
            else min(1.0, expected_base * item["occupancy_modifier"] * item["guest_modifier"])
        )
        pool_probability_valid &= math.isclose(item["base_probability"], expected_base, abs_tol=1e-12)
        pool_probability_valid &= math.isclose(item["final_probability"], expected_final, abs_tol=1e-12)
        if item["daily_classification"] == "AWAY_DAY":
            pool_probability_valid &= not item["activated"]
    pool_events_valid = all(
        2.0 <= event["duration_hours"] <= 5.0
        and 2.0 <= event["power_kw"] <= 5.0
        and datetime.fromisoformat(event["date"] + "T08:00:00+02:00")
        <= datetime.fromisoformat(event["start"])
        <= datetime.fromisoformat(event["date"] + "T14:00:00+02:00")
        and math.isclose(
            (datetime.fromisoformat(event["end"]) - datetime.fromisoformat(event["start"])).total_seconds() / 3600,
            event["duration_hours"],
            abs_tol=1e-9,
        )
        and math.isclose(
            event["required_energy_kwh"],
            event["power_kw"] * event["duration_hours"],
            abs_tol=1e-9,
        )
        and math.isclose(event["required_energy_kwh"], event["allocated_energy_kwh"], abs_tol=1e-8)
        and all(
            _overlap_hours(
                datetime.fromisoformat(event["start"]),
                datetime.fromisoformat(event["end"]),
                away_start,
                away_end,
            )
            == 0
            for away_start, away_end in away_intervals
        )
        for event in ledger["pool_heating_events"]
    )
    sauna_probability_valid = all(
        math.isclose(
            item["final_probability"],
            0.0
            if item["daily_classification"] == "AWAY_DAY"
            else min(1.0, item["base_probability"] * item["guest_modifier"]),
            abs_tol=1e-12,
        )
        and (item["daily_classification"] != "AWAY_DAY" or not item["activated"])
        for item in ledger["sauna_daily_activation"]
    )
    sauna_events_valid = all(
        1.0 <= event["duration_hours"] <= 2.0
        and 6.0 <= event["power_kw"] <= 9.0
        and datetime.fromisoformat(event["date"] + "T19:00:00+02:00")
        <= datetime.fromisoformat(event["start"])
        <= datetime.fromisoformat(event["date"] + "T22:00:00+02:00")
        and math.isclose(
            (datetime.fromisoformat(event["end"]) - datetime.fromisoformat(event["start"])).total_seconds() / 3600,
            event["duration_hours"],
            abs_tol=1e-9,
        )
        and math.isclose(
            event["required_energy_kwh"],
            event["power_kw"] * event["duration_hours"],
            abs_tol=1e-9,
        )
        and math.isclose(event["required_energy_kwh"], event["allocated_energy_kwh"], abs_tol=1e-8)
        and all(
            _overlap_hours(
                datetime.fromisoformat(event["start"]),
                datetime.fromisoformat(event["end"]),
                away_start,
                away_end,
            )
            == 0
            for away_start, away_end in away_intervals
        )
        for event in ledger["sauna_events"]
    )

    checks = {
        "exactly_1464_rows": len(rows) == 1_464,
        "exact_stage2_timestamps": [row["timestamp"] for row in rows]
        == [row["timestamp"] for row in source],
        "exact_stage3a_timestamps": [row["timestamp"] for row in rows]
        == [row["timestamp"] for row in stage3a],
        "no_duplicate_timestamps": len(timestamps) == len(set(timestamps)),
        "hourly_continuity": all(b - a == timedelta(hours=1) for a, b in zip(utc, utc[1:])),
        "timezone_preserved": all(ts.utcoffset() == timedelta(hours=2) for ts in timestamps),
        "no_negative_energy": general_nonnegative,
        "totals_match_components": totals_match,
        "sampled_parameters_in_ranges": all(parameter_checks.values()),
        "hvac_targets_follow_occupancy": targets_valid,
        "hvac_heating_cooling_mutually_exclusive": mutually_exclusive,
        "hvac_controller_hysteresis_valid": controller_valid,
        "hvac_thermal_recurrence_valid": recurrence_valid,
        "hvac_initialization_valid": initialization_valid,
        "ev_ids_exact": ev_ids_valid,
        "ev_leave_probability_structure_valid": ordinary_probability_valid,
        "ev_charging_energy_accounting_valid": charging_energy_valid,
        "ev_hourly_power_cap_valid": charging_cap_valid,
        "ev_charging_only_while_home": charging_home_valid,
        "ev_charging_before_next_departure": charging_before_departure,
        "ev_away_ordinary_generation_mutually_exclusive": away_mutual_exclusion,
        "pool_circulation_runtime_windows_energy_valid": circulation_valid,
        "pool_heating_probability_valid": pool_probability_valid,
        "pool_heating_events_valid_and_outside_away": pool_events_valid,
        "sauna_probability_valid": sauna_probability_valid,
        "sauna_events_valid_and_outside_away": sauna_events_valid,
        "no_stage3a_component_columns": not any(
            column in columns
            for column in (
                "refrigerator_kwh",
                "cooking_kwh",
                "dishwasher_kwh",
                "washer_kwh",
                "dryer_kwh",
            )
        ),
    }
    report = {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "parameter_checks": parameter_checks,
        "row_count": len(rows),
        "first_timestamp": rows[0]["timestamp"] if rows else None,
        "last_timestamp": rows[-1]["timestamp"] if rows else None,
        "component_energy_totals_kwh": metadata["component_energy_totals_kwh"],
        "stage3b_total_energy_kwh": metadata["stage3b_total_energy_kwh"],
    }
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report

