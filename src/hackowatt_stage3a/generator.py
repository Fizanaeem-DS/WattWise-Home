"""Deterministic Stage 3A state, event, and energy generation."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
import csv
import json
import math
from pathlib import Path
import random
from typing import Any
from zoneinfo import ZoneInfo

from .config import (
    COMPONENT_COLUMNS,
    EVENT_LEDGER_OUTPUT,
    HOURLY_OUTPUT,
    METADATA_OUTPUT,
    RANDOM_SEED,
    STAGE2_INPUT,
    STATE_COLUMNS,
    TIMEZONE,
)


OCCUPANT_COMPONENTS = (
    "cooking_kwh",
    "dishwasher_kwh",
    "washer_kwh",
    "dryer_kwh",
    "electronics_kwh",
    "phone_tablet_kwh",
    "interior_lighting_kwh",
)


def _at(day: date, hour: float, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time(0), tzinfo=zone) + timedelta(hours=hour)


def _choice(rng: random.Random, weighted: list[tuple[str, float]]) -> str:
    draw = rng.random()
    cumulative = 0.0
    for value, probability in weighted:
        cumulative += probability
        if draw < cumulative:
            return value
    return weighted[-1][0]


def _overlap_hours(
    start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime
) -> float:
    return max(0.0, (min(end_a, end_b) - max(start_a, start_b)).total_seconds() / 3600)


def _interval_overlaps(
    start: datetime, end: datetime, intervals: list[dict[str, Any]]
) -> bool:
    return any(_overlap_hours(start, end, item["start_dt"], item["end_dt"]) > 0 for item in intervals)


def _active_interval(
    instant: datetime, intervals: list[dict[str, Any]]
) -> dict[str, Any] | None:
    return next(
        (item for item in intervals if item["start_dt"] <= instant < item["end_dt"]),
        None,
    )


def _event_overlapping(
    start: datetime, end: datetime, intervals: list[dict[str, Any]]
) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in intervals
            if _overlap_hours(start, end, item["start_dt"], item["end_dt"]) > 0
        ),
        None,
    )


def _load_stage2(path: Path) -> tuple[list[dict[str, str]], list[datetime]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    timestamps = [datetime.fromisoformat(row["timestamp"]) for row in rows]
    if not rows or len(rows) != 1_464:
        raise ValueError(f"Stage 2 must contain 1,464 rows, found {len(rows)}")
    return rows, timestamps


def _generate_away_events(
    rng: random.Random,
    days: list[date],
    zone: ZoneInfo,
    dataset_end: datetime,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    active_until = _at(days[0], 0, zone)
    categories = [
        ("short_overnight", 0.70, (12.0, 24.0)),
        ("one_full_day", 0.20, (24.0, 36.0)),
        ("two_to_three_days", 0.10, (48.0, 72.0)),
    ]
    for day in days:
        day_start = _at(day, 0, zone)
        if day_start < active_until:
            continue
        if rng.random() >= 0.05:
            continue
        start = _at(day, rng.uniform(6.0, 20.0), zone)
        category_name = _choice(rng, [(name, probability) for name, probability, _ in categories])
        duration_range = next(bounds for name, _, bounds in categories if name == category_name)
        sampled_duration = rng.uniform(*duration_range)
        unclipped_end = start + timedelta(hours=sampled_duration)
        end = min(unclipped_end, dataset_end)
        boundary_clipped = end < unclipped_end
        event = {
            "event_id": f"away_{len(events) + 1:03d}",
            "category": category_name,
            "start_dt": start,
            "end_dt": end,
            "sampled_duration_hours": sampled_duration,
            "actual_duration_hours": (end - start).total_seconds() / 3600,
            "boundary_clipped": boundary_clipped,
        }
        events.append(event)
        active_until = end
    return events


def _generate_daily_states(
    rng: random.Random,
    days: list[date],
    zone: ZoneInfo,
) -> dict[date, dict[str, Any]]:
    states: dict[date, dict[str, Any]] = {}
    for day in days:
        is_weekend = day.weekday() >= 5
        base_day_type = "WE_HOME" if is_weekend else "WD_HOME"
        if is_weekend:
            daytime = _choice(rng, [("EMPTY", 0.20), ("PARTIAL", 0.30), ("FULL", 0.50)])
        else:
            daytime = _choice(rng, [("EMPTY", 0.70), ("PARTIAL", 0.20), ("FULL", 0.10)])

        departure = None
        return_time = None
        if daytime != "FULL":
            if is_weekend:
                departure = _at(day, rng.uniform(10.0, 13.0), zone)
                return_lower = 16.0 if daytime == "EMPTY" else 15.0
                return_time = _at(day, rng.uniform(return_lower, 19.0), zone)
            else:
                departure = _at(day, rng.uniform(8.5, 9.0), zone)
                return_time = _at(day, rng.uniform(16.0, 19.0), zone)

        states[day] = {
            "date": day,
            "base_day_type": base_day_type,
            "is_weekend": is_weekend,
            "daytime_occupancy_state": daytime,
            "departure_dt": departure,
            "return_dt": return_time,
        }
    return states


def _generate_guest_events(
    rng: random.Random,
    days: list[date],
    daily_states: dict[date, dict[str, Any]],
    away_events: list[dict[str, Any]],
    zone: ZoneInfo,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for day in days:
        probability = 0.15 if daily_states[day]["is_weekend"] else 0.05
        if rng.random() >= probability:
            continue
        start = _at(day, rng.uniform(18.0, 20.5), zone)
        sampled_duration = rng.uniform(2.0, 3.0)
        end = min(start + timedelta(hours=sampled_duration), _at(day, 23.5, zone))
        if _interval_overlaps(start, end, away_events):
            continue
        events.append(
            {
                "event_id": f"guest_{len(events) + 1:03d}",
                "start_dt": start,
                "end_dt": end,
                "sampled_duration_hours": sampled_duration,
                "actual_duration_hours": (end - start).total_seconds() / 3600,
                "base_day_type": daily_states[day]["base_day_type"],
            }
        )
    return events


def _serialize_interval_event(event: dict[str, Any]) -> dict[str, Any]:
    serialized = {
        key: (value.isoformat() if isinstance(value, datetime) else value)
        for key, value in event.items()
        if not key.endswith("_dt")
    } | {
        "start": event["start_dt"].isoformat(),
        "end": event["end_dt"].isoformat(),
    }
    if event["event_id"].startswith("away_"):
        serialized.update(
            {
                "away_start": event["start_dt"].isoformat(),
                "away_end": event["end_dt"].isoformat(),
                "away_duration": event["actual_duration_hours"],
                "away_duration_hours": event["actual_duration_hours"],
            }
        )
    return serialized


def generate(
    stage2_path: Path = STAGE2_INPUT,
    hourly_output: Path = HOURLY_OUTPUT,
    ledger_output: Path = EVENT_LEDGER_OUTPUT,
    metadata_output: Path = METADATA_OUTPUT,
    seed: int = RANDOM_SEED,
) -> dict[str, Any]:
    rng = random.Random(seed)
    zone = ZoneInfo(TIMEZONE)
    weather_rows, timestamps = _load_stage2(stage2_path)
    dataset_start = timestamps[0]
    dataset_end = timestamps[-1] + timedelta(hours=1)
    days = sorted({timestamp.date() for timestamp in timestamps})
    index_by_timestamp = {timestamp: index for index, timestamp in enumerate(timestamps)}

    household_parameters = {
        "refrigerator_daily_kwh": rng.uniform(1.5, 2.2),
        "smart_home_base_kw": rng.uniform(0.05, 0.15),
        "oven_kw": rng.uniform(2.0, 2.5),
        "hob_kw": rng.uniform(1.5, 4.0),
        "tv_kw": rng.uniform(0.10, 0.20),
        "computer_kw": rng.uniform(0.05, 0.25),
        "installed_lighting_kw": rng.uniform(0.10, 0.40),
    }

    away_events = _generate_away_events(rng, days, zone, dataset_end)
    daily_states = _generate_daily_states(rng, days, zone)
    guest_events = _generate_guest_events(rng, days, daily_states, away_events, zone)

    row_states: list[dict[str, Any]] = []
    for timestamp in timestamps:
        midpoint = timestamp + timedelta(minutes=30)
        away_event = _active_interval(midpoint, away_events)
        guest_event = _active_interval(midpoint, guest_events)
        state = daily_states[timestamp.date()]
        if away_event:
            occupancy = "EMPTY"
            effective_day_type = "AWAY"
        elif state["daytime_occupancy_state"] == "FULL":
            occupancy = "FULL"
            effective_day_type = state["base_day_type"]
        elif state["departure_dt"] <= midpoint < state["return_dt"]:
            occupancy = state["daytime_occupancy_state"]
            effective_day_type = state["base_day_type"]
        else:
            occupancy = "FULL"
            effective_day_type = state["base_day_type"]
        row_states.append(
            {
                "timestamp": timestamp.isoformat(),
                "day_type": effective_day_type,
                "base_day_type": state["base_day_type"],
                "is_weekend": state["is_weekend"],
                "daytime_occupancy_state": state["daytime_occupancy_state"],
                "occupancy_state": occupancy,
                "away": bool(away_event),
                "away_event_id": away_event["event_id"] if away_event else "",
                "guest_event": bool(guest_event),
                "guest_event_id": guest_event["event_id"] if guest_event else "",
                "household_departure": (
                    state["departure_dt"].isoformat() if state["departure_dt"] else ""
                ),
                "household_return": (
                    state["return_dt"].isoformat() if state["return_dt"] else ""
                ),
            }
        )

    loads = {component: [0.0] * len(timestamps) for component in COMPONENT_COLUMNS}
    appliance_events: list[dict[str, Any]] = []

    def add_event(
        event_type: str,
        component: str,
        start: datetime,
        duration_hours: float,
        energy_kwh: float,
        **attributes: Any,
    ) -> dict[str, Any]:
        end = start + timedelta(hours=duration_hours)
        if start < dataset_start or end > dataset_end:
            raise ValueError(f"Event outside Stage 2 timeline: {event_type} {start} to {end}")
        event_id = f"{event_type}_{sum(e['event_type'] == event_type for e in appliance_events) + 1:03d}"
        power_kw = energy_kwh / duration_hours
        allocations = []
        first_hour = start.replace(minute=0, second=0, microsecond=0)
        cursor = first_hour
        while cursor < end:
            next_hour = cursor + timedelta(hours=1)
            overlap = _overlap_hours(start, end, cursor, next_hour)
            if overlap > 0 and cursor in index_by_timestamp:
                allocated = power_kw * overlap
                loads[component][index_by_timestamp[cursor]] += allocated
                allocations.append(
                    {"timestamp": cursor.isoformat(), "energy_kwh": allocated}
                )
            cursor = next_hour
        allocated_total = sum(item["energy_kwh"] for item in allocations)
        if not math.isclose(allocated_total, energy_kwh, rel_tol=0, abs_tol=1e-9):
            raise ValueError(
                f"Energy allocation failed for {event_id}: {allocated_total} != {energy_kwh}"
            )
        event = {
            "event_id": event_id,
            "event_type": event_type,
            "component": component,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "duration_hours": duration_hours,
            "sampled_energy_kwh": energy_kwh,
            "average_power_kw": power_kw,
            "allocated_energy_kwh": allocated_total,
            "allocations": allocations,
            **attributes,
        }
        appliance_events.append(event)
        return event

    # Fixed refrigerator profile: deterministic +/-8% sinusoid, normalized daily.
    raw_fridge_weights = [1.0 + 0.08 * math.sin(2 * math.pi * hour / 24) for hour in range(24)]
    normalized_fridge_weights = [value / sum(raw_fridge_weights) for value in raw_fridge_weights]
    for day in days:
        for hour in range(24):
            timestamp = _at(day, hour, zone)
            loads["refrigerator_kwh"][index_by_timestamp[timestamp]] = (
                household_parameters["refrigerator_daily_kwh"]
                * normalized_fridge_weights[hour]
            )
    loads["smart_home_base_kwh"] = [
        household_parameters["smart_home_base_kw"] for _ in timestamps
    ]

    def choose_composition(options: list[tuple[str, float]]) -> str:
        return _choice(rng, options)

    def cooking_power(composition: str) -> float:
        return (
            (household_parameters["hob_kw"] if composition in {"hob_only", "both"} else 0.0)
            + (household_parameters["oven_kw"] if composition in {"oven_only", "both"} else 0.0)
        )

    for day in days:
        state = daily_states[day]
        day_guest = next((event for event in guest_events if event["start_dt"].date() == day), None)

        # Morning cooking.
        if rng.random() < 0.35:
            duration = rng.uniform(0.25, 0.75)
            start = _at(day, rng.uniform(6.5, 8.5), zone)
            end = start + timedelta(hours=duration)
            if not _interval_overlaps(start, end, away_events):
                composition = choose_composition(
                    [("hob_only", 0.50), ("oven_only", 0.20), ("both", 0.30)]
                )
                power = cooking_power(composition)
                add_event(
                    "morning_cooking",
                    "cooking_kwh",
                    start,
                    duration,
                    power * duration,
                    composition=composition,
                    guest_event_id="",
                )

        # Consolidated evening dinner.
        if rng.random() < 0.80:
            duration = rng.uniform(0.5, 1.5)
            start = _at(day, rng.uniform(18.0, 21.0), zone)
            end = start + timedelta(hours=duration)
            if not _interval_overlaps(start, end, away_events):
                during_guest = day_guest and _overlap_hours(
                    start, end, day_guest["start_dt"], day_guest["end_dt"]
                ) > 0
                options = (
                    [("hob_only", 0.35), ("oven_only", 0.15), ("both", 0.50)]
                    if during_guest
                    else [("hob_only", 0.50), ("oven_only", 0.20), ("both", 0.30)]
                )
                composition = choose_composition(options)
                power = cooking_power(composition)
                add_event(
                    "dinner",
                    "cooking_kwh",
                    start,
                    duration,
                    power * duration,
                    composition=composition,
                    guest_event_id=day_guest["event_id"] if during_guest else "",
                )

        # Dishwasher.
        dishwasher_probability = min(1.0, 0.50 + (0.25 if day_guest else 0.0))
        if rng.random() < dishwasher_probability:
            duration = rng.uniform(1.0, 2.0)
            latest_start = min(_at(day, 23.0, zone), dataset_end - timedelta(hours=duration))
            earliest_start = _at(day, 20.0, zone)
            if latest_start >= earliest_start:
                start_span = (latest_start - earliest_start).total_seconds() / 3600
                start = earliest_start + timedelta(hours=rng.uniform(0.0, start_span))
                end = start + timedelta(hours=duration)
                if not _interval_overlaps(start, end, away_events):
                    add_event(
                        "dishwasher",
                        "dishwasher_kwh",
                        start,
                        duration,
                        rng.uniform(0.8, 1.2),
                        guest_event_id=day_guest["event_id"] if day_guest else "",
                    )

        # Laundry sequence based on the day's sampled daytime occupancy state.
        laundry_probability = {"FULL": 0.30, "PARTIAL": 0.20, "EMPTY": 0.05}[
            state["daytime_occupancy_state"]
        ]
        if rng.random() < laundry_probability:
            washer_duration = rng.uniform(1.0, 1.5)
            dryer_generated = rng.random() < 0.70
            dryer_duration = rng.uniform(1.0, 1.5) if dryer_generated else 0.0
            dryer_delay = rng.uniform(0.0, 0.5) if dryer_generated else 0.0
            sequence_duration = washer_duration + dryer_delay + dryer_duration
            start = _at(day, rng.uniform(9.0, 19.0 - sequence_duration), zone)
            sequence_end = start + timedelta(hours=sequence_duration)
            if not _interval_overlaps(start, sequence_end, away_events):
                washer = add_event(
                    "washer",
                    "washer_kwh",
                    start,
                    washer_duration,
                    rng.uniform(0.6, 1.0),
                    daytime_occupancy_state=state["daytime_occupancy_state"],
                )
                if dryer_generated:
                    dryer_start = start + timedelta(hours=washer_duration + dryer_delay)
                    add_event(
                        "dryer",
                        "dryer_kwh",
                        dryer_start,
                        dryer_duration,
                        rng.uniform(1.5, 2.5),
                        depends_on_event_id=washer["event_id"],
                        delay_after_washer_hours=dryer_delay,
                    )

        # Daytime computer.
        daytime_probability = {"EMPTY": 0.0, "PARTIAL": 0.35, "FULL": 0.55}[
            state["daytime_occupancy_state"]
        ]
        if rng.random() < daytime_probability:
            duration = rng.uniform(1.0, 3.0)
            start = _at(day, rng.uniform(9.0, 16.0 - duration), zone)
            end = start + timedelta(hours=duration)
            if not _interval_overlaps(start, end, away_events):
                add_event(
                    "daytime_computer",
                    "electronics_kwh",
                    start,
                    duration,
                    household_parameters["computer_kw"] * duration,
                    composition="computer_only",
                )

        # Evening electronics, independent of daytime occupancy.
        evening_probability = 0.85 if day_guest else 0.70
        if rng.random() < evening_probability:
            duration = rng.uniform(1.0, 3.0)
            start = _at(day, rng.uniform(19.0, 23.0 - duration), zone)
            end = start + timedelta(hours=duration)
            if not _interval_overlaps(start, end, away_events):
                composition = choose_composition(
                    [("tv_only", 0.50), ("computer_only", 0.20), ("both", 0.30)]
                )
                power = (
                    (household_parameters["tv_kw"] if composition in {"tv_only", "both"} else 0.0)
                    + (
                        household_parameters["computer_kw"]
                        if composition in {"computer_only", "both"}
                        else 0.0
                    )
                )
                add_event(
                    "evening_electronics",
                    "electronics_kwh",
                    start,
                    duration,
                    power * duration,
                    composition=composition,
                    guest_event_id=day_guest["event_id"] if day_guest else "",
                )

        # Four aggregate phone/tablet devices; energy is assigned to one hour.
        for device_number in range(1, 5):
            if rng.random() >= 0.70:
                continue
            selected_hour = rng.randint(18, 23)
            start = _at(day, float(selected_hour), zone)
            end = start + timedelta(hours=1)
            if end > dataset_end or _interval_overlaps(start, end, away_events):
                continue
            add_event(
                "phone_tablet_charge",
                "phone_tablet_kwh",
                start,
                1.0,
                rng.uniform(0.005, 0.02),
                aggregate_device_id=f"mobile_{device_number}",
            )

    # Lighting is an hourly time-conditioned state load.
    for index, (timestamp, weather, state) in enumerate(
        zip(timestamps, weather_rows, row_states)
    ):
        dark = float(weather["shortwave_radiation"]) <= 0.0
        if not dark:
            continue
        lighting_kw = household_parameters["installed_lighting_kw"]
        if not state["away"]:
            base_fraction = {"FULL": 1.0, "PARTIAL": 0.60, "EMPTY": 0.0}[
                state["occupancy_state"]
            ]
            if state["guest_event"] and state["occupancy_state"] in {"FULL", "PARTIAL"}:
                base_fraction = 1.0
            loads["interior_lighting_kwh"][index] = lighting_kw * base_fraction
        loads["exterior_security_lighting_kwh"][index] = lighting_kw * 0.25

    # Round components first, then calculate total from exactly the serialized values.
    output_rows: list[dict[str, Any]] = []
    for index, state in enumerate(row_states):
        component_values = {
            component: round(loads[component][index], 9) for component in COMPONENT_COLUMNS
        }
        output_rows.append(
            {
                **state,
                **component_values,
                "stage3a_total_kwh": round(sum(component_values.values()), 9),
            }
        )

    hourly_output.parent.mkdir(parents=True, exist_ok=True)
    fields = [*STATE_COLUMNS, *COMPONENT_COLUMNS, "stage3a_total_kwh"]
    with hourly_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)

    ledger = {
        "random_seed": seed,
        "away_events": [_serialize_interval_event(event) for event in away_events],
        "guest_events": [_serialize_interval_event(event) for event in guest_events],
        "daily_states": [
            {
                "date": day.isoformat(),
                "base_day_type": state["base_day_type"],
                "is_weekend": state["is_weekend"],
                "daytime_occupancy_state": state["daytime_occupancy_state"],
                "household_departure": (
                    state["departure_dt"].isoformat() if state["departure_dt"] else None
                ),
                "household_return": (
                    state["return_dt"].isoformat() if state["return_dt"] else None
                ),
            }
            for day, state in daily_states.items()
        ],
        "appliance_events": appliance_events,
    }
    ledger_output.write_text(
        json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    component_totals = {
        component: round(sum(float(row[component]) for row in output_rows), 6)
        for component in COMPONENT_COLUMNS
    }
    metadata = {
        "stage": "3A - base and routine digital-twin loads",
        "random_seed": seed,
        "input_file": str(stage2_path.relative_to(stage2_path.parents[2])).replace("\\", "/"),
        "hourly_output_file": str(hourly_output.relative_to(hourly_output.parents[2])).replace(
            "\\", "/"
        ),
        "event_ledger_file": str(ledger_output.relative_to(ledger_output.parents[2])).replace(
            "\\", "/"
        ),
        "row_count": len(output_rows),
        "first_timestamp": output_rows[0]["timestamp"],
        "last_timestamp": output_rows[-1]["timestamp"],
        "timezone": TIMEZONE,
        "day_type_hour_counts": dict(Counter(row["day_type"] for row in output_rows)),
        "base_day_type_day_counts": dict(
            Counter(state["base_day_type"] for state in daily_states.values())
        ),
        "away": {
            "event_starts": len(away_events),
            "actual_coverage_hours": round(
                sum(event["actual_duration_hours"] for event in away_events), 6
            ),
            "midpoint_classified_hour_count": sum(row["away"] for row in output_rows),
            "affected_calendar_days": len(
                {
                    timestamp.date()
                    for timestamp, row in zip(timestamps, output_rows)
                    if row["away"]
                }
            ),
            "boundary_clipped_events": sum(event["boundary_clipped"] for event in away_events),
        },
        "occupancy_state_hour_counts": dict(
            Counter(row["occupancy_state"] for row in output_rows)
        ),
        "daytime_occupancy_day_counts": dict(
            Counter(state["daytime_occupancy_state"] for state in daily_states.values())
        ),
        "guest_events": {
            "event_count": len(guest_events),
            "midpoint_classified_hour_count": sum(row["guest_event"] for row in output_rows),
        },
        "sampled_household_parameters": {
            key: round(value, 9) for key, value in household_parameters.items()
        },
        "appliance_event_counts": dict(
            sorted(Counter(event["event_type"] for event in appliance_events).items())
        ),
        "component_energy_totals_kwh": component_totals,
        "stage3a_total_energy_kwh": round(
            sum(float(row["stage3a_total_kwh"]) for row in output_rows), 6
        ),
        "implementation_notes": [
            "All stochastic draws use the documented fixed seed.",
            "Uniform sampling is used within every frozen numeric range.",
            "day_type is the effective hourly state; base_day_type preserves the calendar WD_HOME/WE_HOME context.",
            "Events that would overlap an AWAY interval are not generated.",
            "On the final dataset day, dishwasher start support is restricted only as needed to preserve its full sampled energy inside the frozen timeline.",
            "The refrigerator profile is a deterministic +/-8% sinusoid normalized to the sampled daily energy.",
            "No HVAC, EV, pool-circulation, pool-heating, or sauna electricity is generated.",
        ],
    }
    metadata_output.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return metadata

