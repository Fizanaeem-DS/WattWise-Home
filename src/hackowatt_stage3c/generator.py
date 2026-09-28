"""Build the authoritative Stage 3C profile from frozen Stage 2/3A/3B artifacts."""

from __future__ import annotations

from collections import defaultdict
import csv
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import statistics
from typing import Any

from .config import (
    HOURLY_OUTPUT,
    METADATA_OUTPUT,
    SOURCE_PATHS,
    STAGE2_INPUT,
    STAGE3A_COMPONENT_COLUMNS,
    STAGE3A_INPUT,
    STAGE3A_STATE_COLUMNS,
    STAGE3B_COMPONENT_COLUMNS,
    STAGE3B_INPUT,
    STAGE3B_LEDGER,
    STAGE3B_STATE_COLUMNS,
    TIMEZONE,
    WEATHER_COLUMNS,
)


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _rounded(value: float | Decimal, places: int = 9) -> float:
    return round(float(value), places)


def generate(
    stage2_path: Path = STAGE2_INPUT,
    stage3a_path: Path = STAGE3A_INPUT,
    stage3b_path: Path = STAGE3B_INPUT,
    stage3b_ledger_path: Path = STAGE3B_LEDGER,
    hourly_output: Path = HOURLY_OUTPUT,
    metadata_output: Path = METADATA_OUTPUT,
) -> dict[str, Any]:
    stage2_columns, weather = _read_csv(stage2_path)
    stage3a_columns, stage3a = _read_csv(stage3a_path)
    stage3b_columns, stage3b = _read_csv(stage3b_path)
    required_stage2 = {"timestamp", *WEATHER_COLUMNS}
    required_stage3a = {
        "timestamp",
        *STAGE3A_STATE_COLUMNS,
        *STAGE3A_COMPONENT_COLUMNS,
        "stage3a_total_kwh",
    }
    required_stage3b = {
        "timestamp",
        *STAGE3B_STATE_COLUMNS,
        *STAGE3B_COMPONENT_COLUMNS,
        "stage3b_total_kwh",
    }
    if not required_stage2 <= set(stage2_columns):
        raise ValueError("Frozen Stage 2 input is missing required weather columns")
    if not required_stage3a <= set(stage3a_columns):
        raise ValueError("Frozen Stage 3A input is missing required state or component columns")
    if not required_stage3b <= set(stage3b_columns):
        raise ValueError("Frozen Stage 3B input is missing required state or component columns")
    if len(weather) != 1_464 or len(stage3a) != 1_464 or len(stage3b) != 1_464:
        raise ValueError("Stage 2, Stage 3A, and Stage 3B must each contain exactly 1,464 rows")
    timeline = [row["timestamp"] for row in weather]
    if timeline != [row["timestamp"] for row in stage3a] or timeline != [row["timestamp"] for row in stage3b]:
        raise ValueError("Stage 2, Stage 3A, and Stage 3B timelines do not match exactly")

    output_rows: list[dict[str, str]] = []
    for weather_row, a_row, b_row in zip(weather, stage3a, stage3b):
        if a_row["occupancy_state"] != b_row["occupancy_state"] or a_row["away"] != b_row["away"]:
            raise ValueError(f"Stage 3A/3B state mismatch at {a_row['timestamp']}")
        base_fixed = Decimal(a_row["refrigerator_kwh"]) + Decimal(a_row["smart_home_base_kwh"])
        routine = sum(
            (Decimal(a_row[column]) for column in STAGE3A_COMPONENT_COLUMNS[2:]),
            Decimal(0),
        )
        pool = Decimal(b_row["pool_circulation_kwh"]) + Decimal(b_row["pool_heating_kwh"])
        stage3a_total = Decimal(a_row["stage3a_total_kwh"])
        stage3b_total = Decimal(b_row["stage3b_total_kwh"])
        household_total = stage3a_total + stage3b_total
        row: dict[str, str] = {"timestamp": weather_row["timestamp"]}
        row.update({column: weather_row[column] for column in WEATHER_COLUMNS})
        row.update({column: a_row[column] for column in STAGE3A_STATE_COLUMNS})
        row.update({column: b_row[column] for column in STAGE3B_STATE_COLUMNS})
        row.update({column: a_row[column] for column in STAGE3A_COMPONENT_COLUMNS})
        row["stage3a_total_kwh"] = a_row["stage3a_total_kwh"]
        row.update({column: b_row[column] for column in STAGE3B_COMPONENT_COLUMNS})
        row["stage3b_total_kwh"] = b_row["stage3b_total_kwh"]
        row["base_fixed_kwh"] = _decimal_text(base_fixed)
        row["routine_behavior_kwh"] = _decimal_text(routine)
        row["ev_kwh"] = b_row["ev_total_kwh"]
        row["pool_kwh"] = _decimal_text(pool)
        row["household_total_kwh"] = _decimal_text(household_total)
        output_rows.append(row)

    hourly_output.parent.mkdir(parents=True, exist_ok=True)
    with hourly_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)

    household_values = [Decimal(row["household_total_kwh"]) for row in output_rows]
    stage3a_total_energy = sum((Decimal(row["stage3a_total_kwh"]) for row in output_rows), Decimal(0))
    stage3b_total_energy = sum((Decimal(row["stage3b_total_kwh"]) for row in output_rows), Decimal(0))
    household_total_energy = sum(household_values, Decimal(0))
    category_names = (
        "base_fixed_kwh",
        "routine_behavior_kwh",
        "hvac_kwh",
        "ev_kwh",
        "pool_kwh",
        "sauna_kwh",
    )
    category_totals = {
        name: sum((Decimal(row[name]) for row in output_rows), Decimal(0))
        for name in category_names
    }
    category_shares = {
        name: _rounded(total / household_total_energy * 100)
        for name, total in category_totals.items()
    }

    daily: dict[str, Decimal] = defaultdict(Decimal)
    day_is_weekend: dict[str, bool] = {}
    for row in output_rows:
        day = row["timestamp"][:10]
        daily[day] += Decimal(row["household_total_kwh"])
        day_is_weekend[day] = row["is_weekend"] == "True"
    daily_values = list(daily.values())
    weekday_daily = [total for day, total in daily.items() if not day_is_weekend[day]]
    weekend_daily = [total for day, total in daily.items() if day_is_weekend[day]]

    away_groups: dict[str, list[Decimal]] = {"away": [], "non_away": []}
    for row in output_rows:
        key = "away" if row["away"] == "True" else "non_away"
        away_groups[key].append(Decimal(row["household_total_kwh"]))
    away_diagnostics = {
        key: {
            "hour_count": len(values),
            "total_energy_kwh": _rounded(sum(values, Decimal(0))),
            "mean_hourly_energy_kwh": _rounded(statistics.mean(values)),
            "median_hourly_energy_kwh": _rounded(statistics.median(values)),
        }
        for key, values in away_groups.items()
    }

    leaf_component_names = (
        *STAGE3A_COMPONENT_COLUMNS,
        "heating_kwh",
        "cooling_kwh",
        "ev1_charging_kwh",
        "ev2_charging_kwh",
        "pool_circulation_kwh",
        "pool_heating_kwh",
        "sauna_kwh",
    )
    peak_rows = sorted(
        output_rows,
        key=lambda row: (-Decimal(row["household_total_kwh"]), row["timestamp"]),
    )[:10]
    top_hours = []
    for rank, row in enumerate(peak_rows, start=1):
        component_breakdown = {
            name: _rounded(Decimal(row[name])) for name in leaf_component_names
        }
        main_components = [
            {"component": name, "energy_kwh": energy}
            for name, energy in sorted(
                component_breakdown.items(), key=lambda item: (-item[1], item[0])
            )
            if energy > 0
        ][:5]
        top_hours.append(
            {
                "rank": rank,
                "timestamp": row["timestamp"],
                "household_total_kwh": _rounded(Decimal(row["household_total_kwh"])),
                "stage3a_total_kwh": _rounded(Decimal(row["stage3a_total_kwh"])),
                "stage3b_total_kwh": _rounded(Decimal(row["stage3b_total_kwh"])),
                "category_breakdown_kwh": {
                    name: _rounded(Decimal(row[name])) for name in category_names
                },
                "main_contributing_components": main_components,
            }
        )

    ev_ledger = json.loads(stage3b_ledger_path.read_text(encoding="utf-8"))
    truncated = [event for event in ev_ledger["ev_charging_events"] if event["boundary_truncated"]]
    remaining_energy = sum((Decimal(str(event["remaining_energy_kwh"])) for event in truncated), Decimal(0))

    max_index = max(range(len(output_rows)), key=lambda index: household_values[index])
    metadata = {
        "stage": "3C - final combined digital twin",
        "integration_method": "Deterministic exact-timestamp join; no RNG, resampling, interpolation, scaling, smoothing, or added load.",
        "behavioral_assumptions_added": [],
        "row_count": len(output_rows),
        "first_timestamp": output_rows[0]["timestamp"],
        "last_timestamp": output_rows[-1]["timestamp"],
        "timezone": TIMEZONE,
        "source_sha256": {
            name: _sha256(path) for name, path in SOURCE_PATHS.items()
        },
        "energy_totals_kwh": {
            "stage3a": _rounded(stage3a_total_energy),
            "stage3b": _rounded(stage3b_total_energy),
            "household": _rounded(household_total_energy),
        },
        "hourly_diagnostics_kwh": {
            "mean": _rounded(statistics.mean(household_values)),
            "median": _rounded(statistics.median(household_values)),
            "population_standard_deviation": _rounded(statistics.pstdev(household_values)),
            "minimum": _rounded(min(household_values)),
            "maximum": _rounded(max(household_values)),
            "maximum_timestamp": output_rows[max_index]["timestamp"],
        },
        "daily_diagnostics_kwh": {
            "day_count": len(daily_values),
            "minimum": _rounded(min(daily_values)),
            "mean": _rounded(statistics.mean(daily_values)),
            "median": _rounded(statistics.median(daily_values)),
            "maximum": _rounded(max(daily_values)),
            "weekday_average": _rounded(statistics.mean(weekday_daily)),
            "weekend_average": _rounded(statistics.mean(weekend_daily)),
        },
        "away_hour_diagnostics": away_diagnostics,
        "category_energy_totals_kwh": {
            name: _rounded(total) for name, total in category_totals.items()
        },
        "category_percentage_shares": category_shares,
        "top_10_highest_demand_hours": top_hours,
        "variability_inventory": [
            "weekday/weekend structure",
            "EMPTY/PARTIAL/FULL daytime occupancy",
            "exact AWAY episodes",
            "guest events",
            "cooking occurrence and timing",
            "dishwasher occurrence and timing",
            "laundry occurrence and timing",
            "electronics occurrence and timing",
            "weather-driven HVAC",
            "EV trip and charging variability",
            "pool-circulation runtime and window variability",
            "temperature/occupancy/guest-driven pool-heating activation",
            "sauna selected-day variability",
        ],
        "ev_post_boundary_accounting": {
            "boundary_truncated_event_count": len(truncated),
            "remaining_energy_outside_profile_kwh": _rounded(remaining_energy),
            "included_in_hourly_profile": False,
            "policy": "Ledger requirement is preserved; no row, backward redistribution, or hourly energy is added outside the frozen observation window.",
        },
        "warnings": [
            "Stage 3C is an integration artifact; physical, behavioral, and statistical credibility remains for Stage 4 validation.",
            "Known post-window EV energy remains outside the 1,464-hour historical profile.",
        ],
    }
    metadata_output.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return metadata
