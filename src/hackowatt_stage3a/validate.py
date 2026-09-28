"""Programmatic validation for Stage 3A outputs."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Any

from .config import (
    COMPONENT_COLUMNS,
    EVENT_LEDGER_OUTPUT,
    HOURLY_OUTPUT,
    MAJOR_SYSTEM_NAMES,
    METADATA_OUTPUT,
    STAGE2_INPUT,
    VALIDATION_OUTPUT,
)


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def validate(
    stage2_path: Path = STAGE2_INPUT,
    hourly_path: Path = HOURLY_OUTPUT,
    ledger_path: Path = EVENT_LEDGER_OUTPUT,
    metadata_path: Path = METADATA_OUTPUT,
    report_path: Path = VALIDATION_OUTPUT,
) -> dict[str, Any]:
    _, source_rows = _read_csv(stage2_path)
    columns, rows = _read_csv(hourly_path)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    source_timestamps = [row["timestamp"] for row in source_rows]
    timestamps = [datetime.fromisoformat(row["timestamp"]) for row in rows]
    utc = [timestamp.astimezone(timezone.utc) for timestamp in timestamps]

    component_nonnegative = all(
        float(row[component]) >= 0 for row in rows for component in COMPONENT_COLUMNS
    )
    totals_match = all(
        math.isclose(
            float(row["stage3a_total_kwh"]),
            sum(float(row[component]) for component in COMPONENT_COLUMNS),
            rel_tol=0,
            abs_tol=2e-9,
        )
        for row in rows
    )
    away_suppression = all(
        all(float(row[component]) == 0 for component in (
            "cooking_kwh",
            "dishwasher_kwh",
            "washer_kwh",
            "dryer_kwh",
            "electronics_kwh",
            "phone_tablet_kwh",
            "interior_lighting_kwh",
        ))
        for row in rows
        if row["away"] == "True"
    )
    away_fixed_continue = all(
        float(row["refrigerator_kwh"]) > 0
        and float(row["smart_home_base_kwh"]) > 0
        for row in rows
        if row["away"] == "True"
    )
    params = metadata["sampled_household_parameters"]
    parameter_ranges = {
        "refrigerator_daily_kwh": 1.5 <= params["refrigerator_daily_kwh"] <= 2.2,
        "smart_home_base_kw": 0.05 <= params["smart_home_base_kw"] <= 0.15,
        "oven_kw": 2.0 <= params["oven_kw"] <= 2.5,
        "hob_kw": 1.5 <= params["hob_kw"] <= 4.0,
        "tv_kw": 0.10 <= params["tv_kw"] <= 0.20,
        "computer_kw": 0.05 <= params["computer_kw"] <= 0.25,
        "installed_lighting_kw": 0.10 <= params["installed_lighting_kw"] <= 0.40,
    }
    event_ranges = {
        "dishwasher": all(
            0.8 <= event["sampled_energy_kwh"] <= 1.2
            for event in ledger["appliance_events"]
            if event["event_type"] == "dishwasher"
        ),
        "washer": all(
            0.6 <= event["sampled_energy_kwh"] <= 1.0
            for event in ledger["appliance_events"]
            if event["event_type"] == "washer"
        ),
        "dryer": all(
            1.5 <= event["sampled_energy_kwh"] <= 2.5
            for event in ledger["appliance_events"]
            if event["event_type"] == "dryer"
        ),
    }
    events_by_id = {event["event_id"]: event for event in ledger["appliance_events"]}
    dryer_dependencies = all(
        event.get("depends_on_event_id") in events_by_id
        and events_by_id[event["depends_on_event_id"]]["event_type"] == "washer"
        and datetime.fromisoformat(event["start"])
        >= datetime.fromisoformat(events_by_id[event["depends_on_event_id"]]["end"])
        for event in ledger["appliance_events"]
        if event["event_type"] == "dryer"
    )
    event_energy_preserved = all(
        math.isclose(
            event["sampled_energy_kwh"],
            sum(item["energy_kwh"] for item in event["allocations"]),
            rel_tol=0,
            abs_tol=1e-9,
        )
        and math.isclose(
            event["sampled_energy_kwh"],
            event["allocated_energy_kwh"],
            rel_tol=0,
            abs_tol=1e-9,
        )
        for event in ledger["appliance_events"]
    )
    away_intervals = [
        (datetime.fromisoformat(event["start"]), datetime.fromisoformat(event["end"]))
        for event in ledger["away_events"]
    ]
    away_no_overlap = all(
        end_a <= start_b
        for (_, end_a), (start_b, _) in zip(away_intervals, away_intervals[1:])
    )
    guest_structural = all(
        event["base_day_type"] in {"WD_HOME", "WE_HOME"}
        and 18 <= datetime.fromisoformat(event["start"]).hour <= 20
        and datetime.fromisoformat(event["end"]).time()
        <= datetime.fromisoformat(event["end"]).replace(hour=23, minute=30).time()
        for event in ledger["guest_events"]
    )
    no_major_columns = not any(
        any(system in column.lower() for system in MAJOR_SYSTEM_NAMES) for column in columns
    )

    checks = {
        "exactly_1464_rows": len(rows) == 1_464,
        "stage2_timestamps_preserved_exactly": [row["timestamp"] for row in rows]
        == source_timestamps,
        "no_duplicate_timestamps": len(timestamps) == len(set(timestamps)),
        "hourly_continuity": all(
            later - earlier == timedelta(hours=1) for earlier, later in zip(utc, utc[1:])
        ),
        "timezone_preserved": all(
            timestamp.tzinfo is not None and timestamp.utcoffset() == timedelta(hours=2)
            for timestamp in timestamps
        ),
        "no_negative_component_energy": component_nonnegative,
        "total_equals_component_sum": totals_match,
        "household_parameters_within_ranges": all(parameter_ranges.values()),
        "away_suppresses_occupant_driven_loads": away_suppression,
        "refrigerator_and_base_continue_during_away": away_fixed_continue,
        "guest_events_structurally_valid": guest_structural,
        "occupancy_states_valid": all(
            row["occupancy_state"] in {"EMPTY", "PARTIAL", "FULL"} for row in rows
        ),
        "dishwasher_energy_within_range": event_ranges["dishwasher"],
        "washer_energy_within_range": event_ranges["washer"],
        "dryer_energy_within_range": event_ranges["dryer"],
        "dryer_follows_generated_washer": dryer_dependencies,
        "event_energy_preserved": event_energy_preserved,
        "away_events_do_not_overlap": away_no_overlap,
        "no_stage3b_major_system_columns": no_major_columns,
    }
    report = {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "parameter_range_checks": parameter_ranges,
        "event_range_checks": event_ranges,
        "row_count": len(rows),
        "first_timestamp": rows[0]["timestamp"] if rows else None,
        "last_timestamp": rows[-1]["timestamp"] if rows else None,
        "component_energy_totals_kwh": metadata["component_energy_totals_kwh"],
        "stage3a_total_energy_kwh": metadata["stage3a_total_energy_kwh"],
    }
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report

