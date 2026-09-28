"""Convert frozen Stage 3 event ledgers into production optimizer inputs."""

from __future__ import annotations

import csv
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Iterable

from constraints.stage7_constraints import get_constraints
from contract.production_schema import (
    AvailabilityInterval,
    HVACHourState,
    HVACModeConstraint,
    HVACProductionConstraint,
    OptimizationRequirements,
    ProductionEventConstraint,
)
from contract.schema import FlexibilityClass as F
from contract.schema import LoadComponent as L
from .config import STAGE3A_LEDGER, STAGE3B_HOURLY, STAGE3B_LEDGER, STAGE3B_METADATA


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _day_at(date_text: str, clock: time, tzinfo) -> datetime:
    return datetime.combine(datetime.fromisoformat(date_text).date(), clock, tzinfo=tzinfo)


def _overlaps(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> bool:
    return start < other_end and end > other_start


def _away_intervals(away_events: Iterable[dict], start: datetime, end: datetime) -> tuple[AvailabilityInterval, ...]:
    intervals = []
    for away in away_events:
        away_start, away_end = _dt(away["start"]), _dt(away["end"])
        if _overlaps(start, end, away_start, away_end):
            intervals.append(AvailabilityInterval(
                _iso(away_start), _iso(away_end), "away", away["event_id"]
            ))
    return tuple(intervals)


def _feasible_start_intervals(
    lower: datetime,
    upper: datetime,
    duration_hours: float,
    away_events: Iterable[dict],
) -> tuple[AvailabilityInterval, ...]:
    """Return starts for which the complete half-open event avoids AWAY."""

    if upper < lower:
        return ()
    duration = timedelta(hours=duration_hours)
    segments = [(lower, upper)]
    for away in sorted(away_events, key=lambda item: item["start"]):
        invalid_lower = _dt(away["start"]) - duration
        invalid_upper = _dt(away["end"])
        next_segments: list[tuple[datetime, datetime]] = []
        for start, end in segments:
            if invalid_upper <= start or invalid_lower >= end:
                next_segments.append((start, end))
                continue
            if start <= invalid_lower:
                next_segments.append((start, min(end, invalid_lower)))
            if invalid_upper <= end:
                next_segments.append((max(start, invalid_upper), end))
        segments = [(start, end) for start, end in next_segments if end >= start]
    return tuple(AvailabilityInterval(_iso(start), _iso(end), "feasible_start") for start, end in segments)


def _simple_start_support(lower: datetime, upper: datetime) -> tuple[AvailabilityInterval, ...]:
    return () if upper < lower else (AvailabilityInterval(_iso(lower), _iso(upper), "feasible_start"),)


def _event(
    *, event_id: str, component: L, flexibility_class: F, date: str,
    energy: float, duration: float, power: float, actual_start: str,
    actual_end: str, provenance: str, **kwargs,
) -> ProductionEventConstraint:
    return ProductionEventConstraint(
        event_id=event_id,
        component=component,
        flexibility_class=flexibility_class,
        date=date,
        energy_kwh=float(energy),
        duration_hours=float(duration),
        power_kw=float(power),
        actual_start=actual_start,
        actual_end=actual_end,
        provenance=provenance,
        **kwargs,
    )


def build_optimization_requirements(
    stage3a_ledger_path: Path = STAGE3A_LEDGER,
    stage3b_ledger_path: Path = STAGE3B_LEDGER,
    stage3b_hourly_path: Path = STAGE3B_HOURLY,
    stage3b_metadata_path: Path = STAGE3B_METADATA,
) -> OptimizationRequirements:
    """Build real Stage 9 inputs without importing the UI mock generator."""

    a = _read_json(Path(stage3a_ledger_path))
    b = _read_json(Path(stage3b_ledger_path))
    meta = _read_json(Path(stage3b_metadata_path))
    away_events = a["away_events"]
    events: list[ProductionEventConstraint] = []

    # Stage 3A coherent appliance cycles.
    appliances = a["appliance_events"]
    washers = {item["event_id"]: item for item in appliances if item["event_type"] == "washer"}
    for item in appliances:
        kind = item["event_type"]
        if kind not in {"dishwasher", "washer", "dryer"}:
            continue
        actual_start, actual_end = _dt(item["start"]), _dt(item["end"])
        date_text = actual_start.date().isoformat()
        if kind == "dishwasher":
            component = L.DISHWASHER
            deadline = _day_at((actual_start + timedelta(days=1)).date().isoformat(), time(6, 30), actual_start.tzinfo)
            lower = actual_start
            dependency = None
            dependency_delay = None
            same_day = False
        else:
            component = L.WASHER if kind == "washer" else L.DRYER
            deadline = _day_at(date_text, time(23, 0), actual_start.tzinfo)
            dependency = item.get("depends_on_event_id")
            dependency_delay = item.get("delay_after_washer_hours")
            lower = actual_start
            if dependency:
                lower = _dt(washers[dependency]["end"])
            same_day = True
        latest_start = deadline - timedelta(hours=float(item["duration_hours"]))
        away = _away_intervals(away_events, lower, deadline)
        events.append(_event(
            event_id=item["event_id"], component=component, flexibility_class=F.SHIFTABLE,
            date=date_text, energy=item["sampled_energy_kwh"], duration=item["duration_hours"],
            power=item["average_power_kw"], actual_start=item["start"], actual_end=item["end"],
            feasible_start=_iso(lower), feasible_end=_iso(latest_start), deadline=_iso(deadline),
            latest_start=_iso(latest_start), availability_intervals=_simple_start_support(lower, latest_start),
            away_intervals=away, depends_on_event_id=dependency,
            dependency_delay_hours=dependency_delay, coherent_cycle=True,
            same_calendar_day=same_day,
            provenance="data/processed/stage3a_event_ledger.json:appliance_events",
        ))

    params = meta["sampled_household_parameters"]

    # Independent, vehicle-specific EV requirements.
    for item in b["ev_charging_events"]:
        start, end = _dt(item["charging_start"]), _dt(item["charging_end"])
        home_start = _dt(item["return"])
        next_departure = item["next_departure"]
        component = L.EV1 if item["ev_id"] == "EV1" else L.EV2
        events.append(_event(
            event_id=item["charging_event_id"], component=component, flexibility_class=F.SHIFTABLE,
            date=start.date().isoformat(), energy=item["required_energy_kwh"],
            duration=(end - start).total_seconds() / 3600.0, power=item["charging_power_kw"],
            actual_start=item["charging_start"], actual_end=item["charging_end"],
            preferred_start=item["charging_start"], feasible_start=_iso(home_start),
            feasible_end=next_departure, deadline=next_departure,
            availability_intervals=(AvailabilityInterval(
                _iso(home_start), next_departure, "vehicle_home", item.get("trip_id")
            ),), availability_semantics="operation", vehicle_id=item["ev_id"],
            next_departure=next_departure, max_power_kw=7.4,
            boundary_truncated=item["boundary_truncated"],
            delivered_in_window_kwh=item["delivered_in_window_kwh"],
            remaining_energy_kwh=item["remaining_energy_kwh"], coherent_cycle=False,
            provenance="data/processed/stage3b_event_ledger.json:ev_charging_events",
        ))

    # One exact daily pool-circulation service requirement.
    circulation_power = float(params["pool_circulation_power_kw"])
    for item in b["pool_circulation_days"]:
        segments = tuple(AvailabilityInterval(w["start"], w["end"], "actual_operation") for w in item["windows"])
        start, end = _dt(item["windows"][0]["start"]), _dt(item["windows"][-1]["end"])
        day_start = _day_at(item["date"], time(0, 0), start.tzinfo)
        deadline = _day_at(item["date"], time(23, 59), start.tzinfo)
        events.append(_event(
            event_id=f"pool_circulation_{item['date']}", component=L.POOL_CIRCULATION,
            flexibility_class=F.SHIFTABLE, date=item["date"], energy=item["required_energy_kwh"],
            duration=item["required_runtime_hours"], power=circulation_power,
            actual_start=_iso(start), actual_end=_iso(end), feasible_start=_iso(day_start),
            feasible_end=_iso(deadline), deadline=_iso(deadline),
            availability_intervals=(AvailabilityInterval(_iso(day_start), _iso(deadline), "operation"),),
            availability_semantics="operation", away_intervals=_away_intervals(away_events, day_start, deadline),
            coherent_cycle=False, same_calendar_day=True, actual_segments=segments,
            provenance="data/processed/stage3b_event_ledger.json:pool_circulation_days",
        ))

    # Pool heating: approved 08:00 start floor and 22:00 completion deadline.
    for item in b["pool_heating_events"]:
        actual_start, actual_end = _dt(item["start"]), _dt(item["end"])
        lower = _day_at(item["date"], time(8, 0), actual_start.tzinfo)
        deadline = _day_at(item["date"], time(22, 0), actual_start.tzinfo)
        upper = deadline - timedelta(hours=float(item["duration_hours"]))
        feasible = _feasible_start_intervals(lower, upper, item["duration_hours"], away_events)
        if not feasible:
            raise ValueError(f"pool heating {item['event_id']} has no feasible optimizer start")
        events.append(_event(
            event_id=item["event_id"], component=L.POOL_HEATING,
            flexibility_class=F.LIMITED_FLEXIBILITY, date=item["date"],
            energy=item["required_energy_kwh"], duration=item["duration_hours"], power=item["power_kw"],
            actual_start=item["start"], actual_end=item["end"], preferred_start=item["start"],
            feasible_start=feasible[0].start, feasible_end=feasible[-1].end,
            deadline=_iso(deadline), latest_start=_iso(upper), availability_intervals=feasible,
            away_intervals=_away_intervals(away_events, lower, deadline), coherent_cycle=True,
            same_calendar_day=True,
            provenance="data/processed/stage3b_event_ledger.json:pool_heating_events",
        ))

    # Sauna: actual preferred start +/-1h, intersected with absolute START bounds.
    for item in b["sauna_events"]:
        preferred = _dt(item["start"])
        absolute_lower = _day_at(item["date"], time(18, 0), preferred.tzinfo)
        absolute_upper = _day_at(item["date"], time(22, 30), preferred.tzinfo)
        lower, upper = max(preferred - timedelta(hours=1), absolute_lower), min(preferred + timedelta(hours=1), absolute_upper)
        feasible = _feasible_start_intervals(lower, upper, item["duration_hours"], away_events)
        if not feasible:
            raise ValueError(f"sauna {item['event_id']} has no feasible optimizer start")
        events.append(_event(
            event_id=item["event_id"], component=L.SAUNA, flexibility_class=F.LIMITED_FLEXIBILITY,
            date=item["date"], energy=item["required_energy_kwh"], duration=item["duration_hours"],
            power=item["power_kw"], actual_start=item["start"], actual_end=item["end"],
            preferred_start=item["start"], feasible_start=feasible[0].start,
            feasible_end=feasible[-1].end, latest_start=_iso(absolute_upper),
            availability_intervals=feasible,
            away_intervals=_away_intervals(away_events, lower, upper + timedelta(hours=item["duration_hours"])),
            coherent_cycle=True, provenance="data/processed/stage3b_event_ledger.json:sauna_events",
        ))

    # HVAC keeps separate mode bands and all recurrence/controller inputs.
    hpref, cpref = float(params["heating_preference_c"]), float(params["cooling_preference_c"])
    hourly_states: list[HVACHourState] = []
    with Path(stage3b_hourly_path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            hourly_states.append(HVACHourState(
                timestamp=row["timestamp"], occupancy_state=row["occupancy_state"],
                away=row["away"].strip().lower() == "true",
                outdoor_temperature_c=float(row["outdoor_temperature_c"]),
                indoor_temperature_c=float(row["indoor_temperature_c"]),
                effective_heating_target_c=float(row["effective_heating_target_c"]),
                effective_cooling_target_c=float(row["effective_cooling_target_c"]),
                actual_mode=row["hvac_mode"],
            ))
    hvac_meta = meta["hvac"]
    hvac = HVACProductionConstraint(
        event_id="hvac_2025-08-01_2025-09-30", component=L.HVAC,
        flexibility_class=F.LIMITED_FLEXIBILITY,
        heating=HVACModeConstraint("heating", hpref, max(hpref - 1, 20), min(hpref + 1, 22), float(params["heating_power_kw"])),
        cooling=HVACModeConstraint("cooling", cpref, max(cpref - 1, 23), min(cpref + 1, 25), float(params["cooling_power_kw"])),
        mutually_exclusive=True, limited_preconditioning=True,
        no_occupied_comfort_violation=True, thermal_time_constant_hours=6.0,
        heating_effect_c_per_hour=1.0, cooling_effect_c_per_hour=-1.0,
        hysteresis_c=0.5, initial_indoor_temperature_c=float(hvac_meta["initial_indoor_temperature_c"]),
        initial_mode=hvac_meta["initial_mode"], hourly_states=tuple(hourly_states),
        provenance="data/processed/stage3b_metadata.json + stage3b_major_systems_hourly.csv",
    )
    return OptimizationRequirements(tuple(get_constraints()), tuple(events), hvac)
