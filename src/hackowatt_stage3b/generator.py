"""Deterministic Stage 3B generator for major household systems."""

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
    EVENT_LEDGER_OUTPUT,
    HOURLY_OUTPUT,
    METADATA_OUTPUT,
    RANDOM_SEED,
    STAGE2_INPUT,
    STAGE3A_INPUT,
    STAGE3A_LEDGER,
    STAGE3A_METADATA,
    TIMEZONE,
)


class NoFeasibleStartError(RuntimeError):
    """Raised when a frozen event cannot fit outside an exact AWAY interval."""


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


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


def _overlap_hours(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> float:
    return max(0.0, (min(a_end, b_end) - max(a_start, b_start)).total_seconds() / 3600)


def _overlaps_any(start: datetime, end: datetime, intervals: list[dict[str, Any]]) -> bool:
    return any(_overlap_hours(start, end, item["start"], item["end"]) > 0 for item in intervals)


def _active_at(instant: datetime, intervals: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((item for item in intervals if item["start"] <= instant < item["end"]), None)


def _random_start_outside_away(
    rng: random.Random,
    day: date,
    lower_hour: float,
    upper_hour: float,
    duration_hours: float,
    away_intervals: list[dict[str, Any]],
    system: str,
) -> tuple[datetime, datetime, bool, int]:
    """Sample once, then rejection-resample start only as frozen; fail if impossible."""
    zone = ZoneInfo(TIMEZONE)
    lower = _at(day, lower_hour, zone)
    upper = _at(day, upper_hour, zone)
    duration = timedelta(hours=duration_hours)

    # Determine whether any feasible start exists before stochastic rejection sampling.
    segments = [(lower, upper)]
    for away in away_intervals:
        forbidden_lower = away["start"] - duration
        forbidden_upper = away["end"]
        updated: list[tuple[datetime, datetime]] = []
        for start, end in segments:
            if forbidden_upper <= start or forbidden_lower >= end:
                updated.append((start, end))
                continue
            if start <= forbidden_lower:
                updated.append((start, min(end, forbidden_lower)))
            if forbidden_upper <= end:
                updated.append((max(start, forbidden_upper), end))
        segments = [(start, end) for start, end in updated if start <= end]
    if not segments:
        raise NoFeasibleStartError(
            f"{system} activated on {day.isoformat()} with duration {duration_hours:.6f} h, "
            f"but no complete event fits in {lower_hour:02.0f}:00-{upper_hour:02.0f}:00 "
            "outside exact AWAY intervals"
        )

    initial = lower + timedelta(seconds=rng.random() * (upper - lower).total_seconds())
    if not _overlaps_any(initial, initial + duration, away_intervals):
        return initial, initial, False, 0
    # A boundary-touching start can be the sole feasible solution. Continuous
    # rejection sampling cannot draw a zero-width point, so select that exact
    # frozen-range start rather than incorrectly reporting sampling failure.
    if segments and all(start == end for start, end in segments):
        candidate = segments[0][0]
        if not _overlaps_any(candidate, candidate + duration, away_intervals):
            return candidate, initial, True, 1
    attempts = 0
    while attempts < 100_000:
        attempts += 1
        candidate = lower + timedelta(seconds=rng.random() * (upper - lower).total_seconds())
        if not _overlaps_any(candidate, candidate + duration, away_intervals):
            return candidate, initial, True, attempts
    raise RuntimeError(f"Failed to sample feasible {system} start despite non-empty support")


def _allocate_constant_power(
    start: datetime,
    end: datetime,
    power_kw: float,
    timestamps: list[datetime],
    index_by_timestamp: dict[datetime, int],
    target: list[float],
    dataset_start: datetime,
    dataset_end: datetime,
) -> tuple[list[dict[str, Any]], float]:
    allocations: list[dict[str, Any]] = []
    cursor = start.replace(minute=0, second=0, microsecond=0)
    while cursor < end:
        next_hour = cursor + timedelta(hours=1)
        observed_start = max(start, cursor, dataset_start)
        observed_end = min(end, next_hour, dataset_end)
        overlap = max(0.0, (observed_end - observed_start).total_seconds() / 3600)
        if overlap > 0 and cursor in index_by_timestamp:
            energy = power_kw * overlap
            target[index_by_timestamp[cursor]] += energy
            allocations.append({"timestamp": cursor.isoformat(), "energy_kwh": energy})
        cursor = next_hour
        if cursor >= dataset_end and cursor < end:
            break
    return allocations, sum(item["energy_kwh"] for item in allocations)


def generate(
    stage2_path: Path = STAGE2_INPUT,
    stage3a_path: Path = STAGE3A_INPUT,
    stage3a_ledger_path: Path = STAGE3A_LEDGER,
    stage3a_metadata_path: Path = STAGE3A_METADATA,
    hourly_output: Path = HOURLY_OUTPUT,
    ledger_output: Path = EVENT_LEDGER_OUTPUT,
    metadata_output: Path = METADATA_OUTPUT,
    seed: int = RANDOM_SEED,
) -> dict[str, Any]:
    rng = random.Random(seed)
    zone = ZoneInfo(TIMEZONE)
    _, weather = _read_csv(stage2_path)
    _, stage3a = _read_csv(stage3a_path)
    ledger3a = json.loads(stage3a_ledger_path.read_text(encoding="utf-8"))
    metadata3a = json.loads(stage3a_metadata_path.read_text(encoding="utf-8"))
    if len(weather) != 1_464 or len(stage3a) != 1_464:
        raise ValueError("Frozen Stage 2 and Stage 3A inputs must each have 1,464 rows")
    if [row["timestamp"] for row in weather] != [row["timestamp"] for row in stage3a]:
        raise ValueError("Frozen Stage 2 and Stage 3A timelines differ")

    timestamps = [datetime.fromisoformat(row["timestamp"]) for row in weather]
    index_by_timestamp = {timestamp: index for index, timestamp in enumerate(timestamps)}
    dataset_start = timestamps[0]
    dataset_end = timestamps[-1] + timedelta(hours=1)
    days = sorted({timestamp.date() for timestamp in timestamps})

    away_intervals = [
        {
            "event_id": event["event_id"],
            "start": datetime.fromisoformat(event["away_start"]),
            "end": datetime.fromisoformat(event["away_end"]),
        }
        for event in ledger3a["away_events"]
    ]
    guest_by_day = {
        datetime.fromisoformat(event["start"]).date(): event for event in ledger3a["guest_events"]
    }
    daily_state = {date.fromisoformat(item["date"]): item for item in ledger3a["daily_states"]}
    stage3b_day_class: dict[date, str] = {}
    for day in days:
        at_23 = _at(day, 23.0, zone)
        stage3b_day_class[day] = (
            "AWAY_DAY"
            if _active_at(at_23, away_intervals)
            else daily_state[day]["base_day_type"]
        )

    parameters = {
        "heating_power_kw": rng.uniform(1.5, 4.0),
        "cooling_power_kw": rng.uniform(1.0, 2.5),
        "heating_preference_c": rng.uniform(20.0, 22.0),
        "cooling_preference_c": rng.uniform(23.0, 25.0),
        "pool_circulation_power_kw": rng.uniform(0.6, 1.2),
        "pool_heating_power_kw": rng.uniform(2.0, 5.0),
        "sauna_power_kw": rng.uniform(6.0, 9.0),
    }

    # HVAC: one daily jitter shared by normal heating/cooling preferences.
    hvac_days: dict[date, dict[str, float]] = {}
    for day in days:
        jitter = rng.uniform(-0.5, 0.5)
        hvac_days[day] = {
            "comfort_jitter_c": jitter,
            "normal_heating_target_c": min(
                22.0, max(20.0, parameters["heating_preference_c"] + jitter)
            ),
            "normal_cooling_target_c": min(
                25.0, max(23.0, parameters["cooling_preference_c"] + jitter)
            ),
        }

    heating_targets: list[float] = []
    cooling_targets: list[float] = []
    for row, timestamp in zip(stage3a, timestamps):
        normal_heat = hvac_days[timestamp.date()]["normal_heating_target_c"]
        normal_cool = hvac_days[timestamp.date()]["normal_cooling_target_c"]
        if row["away"] == "True":
            heating_targets.append(normal_heat - 3.0)
            cooling_targets.append(normal_cool + 3.0)
        elif row["occupancy_state"] == "EMPTY":
            heating_targets.append(normal_heat - 1.0)
            cooling_targets.append(normal_cool + 1.0)
        else:
            heating_targets.append(normal_heat)
            cooling_targets.append(normal_cool)

    indoor: list[float] = [0.0] * len(timestamps)
    hvac_modes: list[str] = ["off"] * len(timestamps)
    heating = [0.0] * len(timestamps)
    cooling = [0.0] * len(timestamps)
    indoor[0] = (heating_targets[0] + cooling_targets[0]) / 2.0
    for index, timestamp in enumerate(timestamps):
        if index > 0:
            previous = hvac_modes[index - 1]
            if previous == "cool":
                hvac_modes[index] = "off" if indoor[index] <= cooling_targets[index] else "cool"
            elif previous == "heat":
                hvac_modes[index] = "off" if indoor[index] >= heating_targets[index] else "heat"
            elif indoor[index] > cooling_targets[index] + 0.5:
                hvac_modes[index] = "cool"
            elif indoor[index] < heating_targets[index] - 0.5:
                hvac_modes[index] = "heat"
            else:
                hvac_modes[index] = "off"
        if hvac_modes[index] == "heat":
            heating[index] = parameters["heating_power_kw"]
            effect = 1.0
        elif hvac_modes[index] == "cool":
            cooling[index] = parameters["cooling_power_kw"]
            effect = -1.0
        else:
            effect = 0.0
        if index + 1 < len(timestamps):
            outdoor = float(weather[index]["temperature_2m"])
            indoor[index + 1] = indoor[index] + (outdoor - indoor[index]) / 6.0 + effect

    # EV trips: ordinary daily generation is excluded from any date touched by AWAY.
    away_touched_dates: set[date] = set()
    for interval in away_intervals:
        cursor = interval["start"].date()
        while cursor <= (interval["end"] - timedelta(microseconds=1)).date():
            away_touched_dates.add(cursor)
            cursor += timedelta(days=1)

    ev_ids = ("EV1", "EV2")
    trip_events: list[dict[str, Any]] = []
    ordinary_ev_trials: list[dict[str, Any]] = []
    away_ev_outcomes: list[dict[str, Any]] = []
    for interval in away_intervals:
        outcome = _choice(
            rng,
            [("both_travel", 0.50), ("one_travels", 0.40), ("both_remain_home", 0.10)],
        )
        if outcome == "both_travel":
            traveling = ["EV1", "EV2"]
        elif outcome == "one_travels":
            traveling = [rng.choice(ev_ids)]
        else:
            traveling = []
        away_ev_outcomes.append(
            {
                "away_event_id": interval["event_id"],
                "outcome": outcome,
                "traveling_evs": traveling,
                "home_remain_evs": [ev for ev in ev_ids if ev not in traveling],
            }
        )
        for ev_id in traveling:
            trip_events.append(
                {
                    "trip_id": f"{ev_id.lower()}_trip_{sum(t['ev_id'] == ev_id for t in trip_events) + 1:03d}",
                    "ev_id": ev_id,
                    "trip_type": "away",
                    "departure": interval["start"],
                    "return": interval["end"],
                    "used": True,
                    "away_event_id": interval["event_id"],
                    "leave_probability": None,
                    "leave_draw": None,
                }
            )

    for day in days:
        state = daily_state[day]
        for ev_id in ev_ids:
            base_probability = (
                (0.45 if ev_id == "EV1" else 0.40)
                if state["is_weekend"]
                else (0.70 if ev_id == "EV1" else 0.60)
            )
            modifier = {"EMPTY": 1.15, "PARTIAL": 1.0, "FULL": 0.70}[
                state["daytime_occupancy_state"]
            ]
            probability = min(1.0, base_probability * modifier)
            trial = {
                "date": day.isoformat(),
                "ev_id": ev_id,
                "base_day_type": state["base_day_type"],
                "daytime_occupancy_state": state["daytime_occupancy_state"],
                "base_leave_probability": base_probability,
                "occupancy_modifier": modifier,
                "final_leave_probability": probability,
                "eligible": day not in away_touched_dates,
                "used": False,
            }
            if day in away_touched_dates:
                trial["ineligible_reason"] = "calendar date intersects exact AWAY event"
                ordinary_ev_trials.append(trial)
                continue
            draw = rng.random()
            trial["leave_draw"] = draw
            trial["used"] = draw < probability
            ordinary_ev_trials.append(trial)
            if draw >= probability:
                continue
            if state["is_weekend"]:
                departure = _at(day, rng.uniform(9.0, 14.0), zone)
                return_time = _at(day, rng.uniform(15.0, 21.0), zone)
                if return_time <= departure:
                    return_time = departure + timedelta(minutes=1)
            else:
                departure = _at(day, rng.uniform(8.5, 9.0), zone)
                return_time = _at(day, rng.uniform(16.0, 19.0), zone)
            trip_events.append(
                {
                    "trip_id": f"{ev_id.lower()}_trip_{sum(t['ev_id'] == ev_id for t in trip_events) + 1:03d}",
                    "ev_id": ev_id,
                    "trip_type": "ordinary",
                    "departure": departure,
                    "return": return_time,
                    "used": True,
                    "away_event_id": None,
                    "leave_probability": probability,
                    "leave_draw": draw,
                    "base_day_type": state["base_day_type"],
                    "daytime_occupancy_state": state["daytime_occupancy_state"],
                }
            )

    trip_events.sort(key=lambda item: (item["ev_id"], item["departure"]))
    ev_loads = {ev_id: [0.0] * len(timestamps) for ev_id in ev_ids}
    charging_events: list[dict[str, Any]] = []
    for trip in trip_events:
        charge_draw = rng.random()
        requires_charge = charge_draw < 0.70
        trip["requires_charge"] = requires_charge
        trip["charge_requirement_draw"] = charge_draw
        if not requires_charge:
            trip.update({"energy_tier": None, "required_energy_kwh": 0.0})
            continue
        tier = _choice(rng, [("LOW", 0.45), ("MEDIUM", 0.40), ("HIGH", 0.15)])
        bounds = {"LOW": (6.0, 12.0), "MEDIUM": (12.0, 24.0), "HIGH": (24.0, 40.0)}[tier]
        required = rng.uniform(*bounds)
        delay = rng.uniform(0.0, 1.0)
        charge_start = trip["return"] + timedelta(hours=delay)
        charge_end = charge_start + timedelta(hours=required / 7.4)
        future_departures = [
            item["departure"]
            for item in trip_events
            if item["ev_id"] == trip["ev_id"] and item["departure"] > trip["return"]
        ]
        next_departure = min(future_departures) if future_departures else None
        if next_departure is not None and charge_end > next_departure:
            raise RuntimeError(
                f"Infeasible frozen EV requirement for {trip['trip_id']}: charging ends "
                f"{charge_end.isoformat()} after next departure {next_departure.isoformat()}"
            )
        allocations, delivered = _allocate_constant_power(
            charge_start,
            charge_end,
            7.4,
            timestamps,
            index_by_timestamp,
            ev_loads[trip["ev_id"]],
            dataset_start,
            dataset_end,
        )
        remaining = max(0.0, required - delivered)
        boundary_truncated = remaining > 1e-9
        event = {
            "charging_event_id": f"{trip['ev_id'].lower()}_charge_{sum(e['ev_id'] == trip['ev_id'] for e in charging_events) + 1:03d}",
            "trip_id": trip["trip_id"],
            "ev_id": trip["ev_id"],
            "trip_type": trip["trip_type"],
            "departure": trip["departure"].isoformat(),
            "return": trip["return"].isoformat(),
            "requires_charge": True,
            "energy_tier": tier,
            "required_energy_kwh": required,
            "charging_delay_hours": delay,
            "charging_start": charge_start.isoformat(),
            "charging_end": charge_end.isoformat(),
            "charging_power_kw": 7.4,
            "next_departure": next_departure.isoformat() if next_departure else None,
            "boundary_truncated": boundary_truncated,
            "delivered_in_window_kwh": delivered,
            "remaining_energy_kwh": remaining,
            "allocations": allocations,
            "away_event_id": trip.get("away_event_id"),
        }
        charging_events.append(event)
        trip.update(
            {
                "energy_tier": tier,
                "required_energy_kwh": required,
                "charging_event_id": event["charging_event_id"],
            }
        )

    ev_home = {ev_id: [] for ev_id in ev_ids}
    ev_home_fraction = {ev_id: [] for ev_id in ev_ids}
    for ev_id in ev_ids:
        ev_trips = [item for item in trip_events if item["ev_id"] == ev_id]
        for timestamp in timestamps:
            hour_end = timestamp + timedelta(hours=1)
            absent_hours = sum(
                _overlap_hours(timestamp, hour_end, item["departure"], item["return"])
                for item in ev_trips
            )
            home_fraction = max(0.0, min(1.0, 1.0 - absent_hours))
            ev_home_fraction[ev_id].append(home_fraction)
            ev_home[ev_id].append(home_fraction > 0.0)

    # Pool circulation daily service.
    pool_circulation = [0.0] * len(timestamps)
    circulation_days: list[dict[str, Any]] = []
    for day in days:
        daily_class = stage3b_day_class[day]
        runtime = rng.uniform(4.0, 6.0) if daily_class == "AWAY_DAY" else rng.uniform(6.0, 10.0)
        window_count = 1 if rng.random() < 0.30 else 2
        windows: list[tuple[datetime, datetime]] = []
        if window_count == 1:
            start = _at(day, rng.uniform(8.0, 12.0), zone)
            windows = [(start, start + timedelta(hours=runtime))]
            split_fraction = None
        else:
            split_fraction = rng.uniform(0.50, 0.70)
            first_duration = runtime * split_fraction
            second_duration = runtime - first_duration
            for _ in range(100_000):
                first_start = _at(day, rng.uniform(6.0, 9.0), zone)
                second_start = _at(day, rng.uniform(15.0, 18.0), zone)
                first_end = first_start + timedelta(hours=first_duration)
                second_end = second_start + timedelta(hours=second_duration)
                if first_end <= second_start and second_end <= _at(day, 24.0, zone):
                    windows = [(first_start, first_end), (second_start, second_end)]
                    break
            if not windows:
                raise RuntimeError(f"No feasible circulation placement for {day.isoformat()}")
        serialized_windows = []
        allocated_energy = 0.0
        for start, end in windows:
            allocations, energy = _allocate_constant_power(
                start,
                end,
                parameters["pool_circulation_power_kw"],
                timestamps,
                index_by_timestamp,
                pool_circulation,
                dataset_start,
                dataset_end,
            )
            allocated_energy += energy
            serialized_windows.append(
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "duration_hours": (end - start).total_seconds() / 3600,
                    "allocations": allocations,
                }
            )
        circulation_days.append(
            {
                "date": day.isoformat(),
                "daily_classification": daily_class,
                "required_runtime_hours": runtime,
                "window_count": window_count,
                "first_window_fraction": split_fraction,
                "windows": serialized_windows,
                "required_energy_kwh": runtime * parameters["pool_circulation_power_kw"],
                "allocated_energy_kwh": allocated_energy,
            }
        )

    # Pool heating daily activation and coherent events.
    pool_heating = [0.0] * len(timestamps)
    pool_heating_daily: list[dict[str, Any]] = []
    pool_heating_events: list[dict[str, Any]] = []
    weather_by_day: dict[date, list[float]] = {day: [] for day in days}
    for row, timestamp in zip(weather, timestamps):
        weather_by_day[timestamp.date()].append(float(row["temperature_2m"]))
    for day in days:
        mean_temp = sum(weather_by_day[day]) / len(weather_by_day[day])
        base_probability = 0.70 if mean_temp < 15 else (0.35 if mean_temp <= 20 else 0.08)
        occupancy = daily_state[day]["daytime_occupancy_state"]
        occupancy_modifier = {"FULL": 1.25, "PARTIAL": 1.0, "EMPTY": 0.60}[occupancy]
        guest_modifier = 1.30 if day in guest_by_day else 1.0
        if stage3b_day_class[day] == "AWAY_DAY":
            final_probability = 0.0
        else:
            final_probability = min(1.0, base_probability * occupancy_modifier * guest_modifier)
        activation_draw = rng.random()
        active = activation_draw < final_probability
        record: dict[str, Any] = {
            "date": day.isoformat(),
            "daily_classification": stage3b_day_class[day],
            "daily_mean_outdoor_temperature_c": mean_temp,
            "base_probability": base_probability,
            "occupancy_state": occupancy,
            "occupancy_modifier": occupancy_modifier,
            "guest_event": day in guest_by_day,
            "guest_modifier": guest_modifier,
            "final_probability": final_probability,
            "activation_draw": activation_draw,
            "activated": active,
            "event_id": None,
        }
        if active:
            duration = rng.uniform(2.0, 5.0)
            start, initial_start, resampled, attempts = _random_start_outside_away(
                rng, day, 8.0, 14.0, duration, away_intervals, "pool heating"
            )
            end = start + timedelta(hours=duration)
            allocations, energy = _allocate_constant_power(
                start,
                end,
                parameters["pool_heating_power_kw"],
                timestamps,
                index_by_timestamp,
                pool_heating,
                dataset_start,
                dataset_end,
            )
            event_id = f"pool_heating_{len(pool_heating_events) + 1:03d}"
            event = {
                "event_id": event_id,
                "date": day.isoformat(),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "initial_sampled_start": initial_start.isoformat(),
                "start_resampled_due_to_away": resampled,
                "resampling_attempts": attempts,
                "duration_hours": duration,
                "power_kw": parameters["pool_heating_power_kw"],
                "required_energy_kwh": parameters["pool_heating_power_kw"] * duration,
                "allocated_energy_kwh": energy,
                "allocations": allocations,
            }
            pool_heating_events.append(event)
            record["event_id"] = event_id
        pool_heating_daily.append(record)

    # Sauna daily activation and coherent events.
    sauna = [0.0] * len(timestamps)
    sauna_daily: list[dict[str, Any]] = []
    sauna_events: list[dict[str, Any]] = []
    for day in days:
        base_probability = 0.25 if daily_state[day]["is_weekend"] else 0.10
        guest_modifier = 1.75 if day in guest_by_day else 1.0
        final_probability = (
            0.0
            if stage3b_day_class[day] == "AWAY_DAY"
            else min(1.0, base_probability * guest_modifier)
        )
        activation_draw = rng.random()
        active = activation_draw < final_probability
        record: dict[str, Any] = {
            "date": day.isoformat(),
            "daily_classification": stage3b_day_class[day],
            "base_probability": base_probability,
            "guest_event": day in guest_by_day,
            "guest_modifier": guest_modifier,
            "final_probability": final_probability,
            "activation_draw": activation_draw,
            "activated": active,
            "event_id": None,
        }
        if active:
            duration = rng.uniform(1.0, 2.0)
            start, initial_start, resampled, attempts = _random_start_outside_away(
                rng, day, 19.0, 22.0, duration, away_intervals, "sauna"
            )
            end = start + timedelta(hours=duration)
            allocations, energy = _allocate_constant_power(
                start,
                end,
                parameters["sauna_power_kw"],
                timestamps,
                index_by_timestamp,
                sauna,
                dataset_start,
                dataset_end,
            )
            event_id = f"sauna_{len(sauna_events) + 1:03d}"
            event = {
                "event_id": event_id,
                "date": day.isoformat(),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "initial_sampled_start": initial_start.isoformat(),
                "start_resampled_due_to_away": resampled,
                "resampling_attempts": attempts,
                "duration_hours": duration,
                "power_kw": parameters["sauna_power_kw"],
                "required_energy_kwh": parameters["sauna_power_kw"] * duration,
                "allocated_energy_kwh": energy,
                "guest_event_id": guest_by_day[day]["event_id"] if day in guest_by_day else None,
                "allocations": allocations,
            }
            sauna_events.append(event)
            record["event_id"] = event_id
        sauna_daily.append(record)

    output_rows: list[dict[str, Any]] = []
    for index, timestamp in enumerate(timestamps):
        hvac_kwh = heating[index] + cooling[index]
        ev1 = ev_loads["EV1"][index]
        ev2 = ev_loads["EV2"][index]
        ev_total = ev1 + ev2
        total = hvac_kwh + ev_total + pool_circulation[index] + pool_heating[index] + sauna[index]
        output_rows.append(
            {
                "timestamp": timestamp.isoformat(),
                "daily_stage3b_classification": stage3b_day_class[timestamp.date()],
                "occupancy_state": stage3a[index]["occupancy_state"],
                "away": stage3a[index]["away"],
                "outdoor_temperature_c": round(float(weather[index]["temperature_2m"]), 9),
                "indoor_temperature_c": round(indoor[index], 9),
                "effective_heating_target_c": round(heating_targets[index], 9),
                "effective_cooling_target_c": round(cooling_targets[index], 9),
                "hvac_mode": hvac_modes[index],
                "heating_kwh": round(heating[index], 9),
                "cooling_kwh": round(cooling[index], 9),
                "hvac_kwh": round(hvac_kwh, 9),
                "ev1_home": ev_home["EV1"][index],
                "ev2_home": ev_home["EV2"][index],
                "ev1_home_fraction": round(ev_home_fraction["EV1"][index], 9),
                "ev2_home_fraction": round(ev_home_fraction["EV2"][index], 9),
                "ev1_charging_kwh": round(ev1, 9),
                "ev2_charging_kwh": round(ev2, 9),
                "ev_total_kwh": round(ev_total, 9),
                "pool_circulation_kwh": round(pool_circulation[index], 9),
                "pool_heating_kwh": round(pool_heating[index], 9),
                "sauna_kwh": round(sauna[index], 9),
                "stage3b_total_kwh": round(total, 9),
            }
        )

    hourly_output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(output_rows[0])
    with hourly_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)

    def serialize_trip(trip: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in trip.items()
        }

    ledger = {
        "random_seed": seed,
        "daily_stage3b_classification": {
            day.isoformat(): classification for day, classification in stage3b_day_class.items()
        },
        "hvac_daily_targets": {
            day.isoformat(): values for day, values in hvac_days.items()
        },
        "ordinary_ev_trials": ordinary_ev_trials,
        "away_ev_outcomes": away_ev_outcomes,
        "ev_trip_events": [serialize_trip(trip) for trip in trip_events],
        "ev_charging_events": charging_events,
        "pool_circulation_days": circulation_days,
        "pool_heating_daily_activation": pool_heating_daily,
        "pool_heating_events": pool_heating_events,
        "sauna_daily_activation": sauna_daily,
        "sauna_events": sauna_events,
    }
    ledger_output.write_text(
        json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    component_totals = {
        "heating_kwh": round(sum(float(row["heating_kwh"]) for row in output_rows), 6),
        "cooling_kwh": round(sum(float(row["cooling_kwh"]) for row in output_rows), 6),
        "hvac_kwh": round(sum(float(row["hvac_kwh"]) for row in output_rows), 6),
        "ev1_charging_kwh": round(sum(float(row["ev1_charging_kwh"]) for row in output_rows), 6),
        "ev2_charging_kwh": round(sum(float(row["ev2_charging_kwh"]) for row in output_rows), 6),
        "ev_total_kwh": round(sum(float(row["ev_total_kwh"]) for row in output_rows), 6),
        "pool_circulation_kwh": round(sum(float(row["pool_circulation_kwh"]) for row in output_rows), 6),
        "pool_heating_kwh": round(sum(float(row["pool_heating_kwh"]) for row in output_rows), 6),
        "sauna_kwh": round(sum(float(row["sauna_kwh"]) for row in output_rows), 6),
    }
    charging_summary = {}
    for ev_id in ev_ids:
        events = [event for event in charging_events if event["ev_id"] == ev_id]
        charging_summary[ev_id] = {
            "event_count": len(events),
            "required_energy_kwh": round(sum(event["required_energy_kwh"] for event in events), 6),
            "delivered_in_window_kwh": round(
                sum(event["delivered_in_window_kwh"] for event in events), 6
            ),
            "remaining_energy_kwh": round(sum(event["remaining_energy_kwh"] for event in events), 6),
            "boundary_truncated_event_count": sum(event["boundary_truncated"] for event in events),
        }
    metadata = {
        "stage": "3B - major household systems",
        "random_seed": seed,
        "reproducibility": "Separate deterministic random.Random seed; frozen Stage 2/3A artifacts are read-only.",
        "input_stage3a_seed": metadata3a["random_seed"],
        "row_count": len(output_rows),
        "first_timestamp": output_rows[0]["timestamp"],
        "last_timestamp": output_rows[-1]["timestamp"],
        "timezone": TIMEZONE,
        "sampled_household_parameters": {key: round(value, 9) for key, value in parameters.items()},
        "hvac": {
            "mode_hour_counts": dict(Counter(hvac_modes)),
            "heating_energy_kwh": component_totals["heating_kwh"],
            "cooling_energy_kwh": component_totals["cooling_kwh"],
            "total_energy_kwh": component_totals["hvac_kwh"],
            "initial_indoor_temperature_c": round(indoor[0], 9),
            "initial_mode": hvac_modes[0],
        },
        "ev": {
            "trip_counts": {
                ev_id: sum(trip["ev_id"] == ev_id for trip in trip_events) for ev_id in ev_ids
            },
            "charging": charging_summary,
            "away_outcome_counts": dict(Counter(item["outcome"] for item in away_ev_outcomes)),
        },
        "pool_circulation": {
            "power_kw": round(parameters["pool_circulation_power_kw"], 9),
            "ordinary_runtime_hours": {
                "min": round(min(item["required_runtime_hours"] for item in circulation_days if item["daily_classification"] != "AWAY_DAY"), 6),
                "max": round(max(item["required_runtime_hours"] for item in circulation_days if item["daily_classification"] != "AWAY_DAY"), 6),
                "mean": round(sum(item["required_runtime_hours"] for item in circulation_days if item["daily_classification"] != "AWAY_DAY") / sum(item["daily_classification"] != "AWAY_DAY" for item in circulation_days), 6),
            },
            "away_runtime_hours": {
                "min": round(min(item["required_runtime_hours"] for item in circulation_days if item["daily_classification"] == "AWAY_DAY"), 6),
                "max": round(max(item["required_runtime_hours"] for item in circulation_days if item["daily_classification"] == "AWAY_DAY"), 6),
                "mean": round(sum(item["required_runtime_hours"] for item in circulation_days if item["daily_classification"] == "AWAY_DAY") / sum(item["daily_classification"] == "AWAY_DAY" for item in circulation_days), 6),
            },
            "window_count_days": dict(Counter(item["window_count"] for item in circulation_days)),
            "total_energy_kwh": component_totals["pool_circulation_kwh"],
        },
        "pool_heating": {
            "power_kw": round(parameters["pool_heating_power_kw"], 9),
            "activated_day_count": len(pool_heating_events),
            "resampled_start_count": sum(event["start_resampled_due_to_away"] for event in pool_heating_events),
            "total_energy_kwh": component_totals["pool_heating_kwh"],
        },
        "sauna": {
            "power_kw": round(parameters["sauna_power_kw"], 9),
            "event_count": len(sauna_events),
            "resampled_start_count": sum(event["start_resampled_due_to_away"] for event in sauna_events),
            "total_energy_kwh": component_totals["sauna_kwh"],
        },
        "component_energy_totals_kwh": component_totals,
        "stage3b_total_energy_kwh": round(
            sum(float(row["stage3b_total_kwh"]) for row in output_rows), 6
        ),
        "warnings": [
            "Stage 3B excludes all Stage 3A energy by design; the combined authoritative artifact belongs to Stage 3C.",
            "Boundary-truncated EV events retain post-window remaining energy in the ledger without extending the hourly dataset.",
        ],
    }
    metadata_output.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return metadata

