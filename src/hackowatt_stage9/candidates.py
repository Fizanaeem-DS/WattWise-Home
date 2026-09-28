"""Deterministic coherent-cycle candidates and interval utilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math

from contract.production_schema import ProductionEventConstraint
from .config import SCHEDULING_RESOLUTION_MINUTES, VALUE_TOLERANCE


@dataclass(frozen=True)
class StartCandidate:
    start: datetime
    end: datetime
    allocations: tuple[tuple[int, float], ...]


def overlap_hours(start: datetime, end: datetime, hour_start: datetime) -> float:
    hour_end = hour_start + timedelta(hours=1)
    return max((min(end, hour_end) - max(start, hour_start)).total_seconds() / 3600.0, 0.0)


def _ceil_grid(value: datetime) -> datetime:
    minute = SCHEDULING_RESOLUTION_MINUTES
    base = value.replace(second=0, microsecond=0)
    remainder = base.minute % minute
    if remainder:
        base += timedelta(minutes=minute - remainder)
    if base < value:
        base += timedelta(minutes=minute)
    return base


def allocate_coherent(
    start: datetime,
    duration_hours: float,
    power_kw: float,
    energy_kwh: float,
    timeline: list[datetime],
) -> tuple[tuple[int, float], ...]:
    end = start + timedelta(hours=duration_hours)
    values = []
    for index, hour in enumerate(timeline):
        overlap = overlap_hours(start, end, hour)
        if overlap > 0:
            values.append([index, power_kw * overlap])
    total = sum(value for _, value in values)
    if total <= 0 or abs(total - energy_kwh) > 1e-5:
        raise RuntimeError(f"STOP: coherent allocation cannot preserve {energy_kwh} kWh")
    values[-1][1] += energy_kwh - total
    if values[-1][1] < -VALUE_TOLERANCE:
        raise RuntimeError("STOP: negative coherent-cycle remainder")
    return tuple((index, float(value)) for index, value in values if value > VALUE_TOLERANCE)


def coherent_candidates(
    event: ProductionEventConstraint,
    timeline: list[datetime],
) -> tuple[StartCandidate, ...]:
    horizon_start, horizon_end = timeline[0], timeline[-1] + timedelta(hours=1)
    starts: set[datetime] = set()
    for interval in event.availability_intervals:
        lower, upper = datetime.fromisoformat(interval.start), datetime.fromisoformat(interval.end)
        starts.update((lower, upper))
        point = _ceil_grid(lower)
        while point <= upper:
            starts.add(point)
            point += timedelta(minutes=SCHEDULING_RESOLUTION_MINUTES)
    actual = datetime.fromisoformat(event.actual_start)
    for interval in event.availability_intervals:
        lower, upper = datetime.fromisoformat(interval.start), datetime.fromisoformat(interval.end)
        if lower <= actual <= upper:
            starts.add(actual)
    candidates = []
    for start in sorted(starts):
        end = start + timedelta(hours=event.duration_hours)
        if start < horizon_start or end > horizon_end:
            continue
        allocations = allocate_coherent(start, event.duration_hours, event.power_kw, event.energy_kwh, timeline)
        candidates.append(StartCandidate(start, end, allocations))
    if not candidates:
        raise RuntimeError(f"STOP: no coherent scheduling candidate for {event.event_id}")
    return tuple(candidates)


def interval_capacity(
    interval_start: datetime,
    interval_end: datetime | None,
    power_kw: float,
    timeline: list[datetime],
) -> dict[int, float]:
    end = interval_end or (timeline[-1] + timedelta(hours=1))
    return {
        index: power_kw * overlap_hours(interval_start, end, hour)
        for index, hour in enumerate(timeline)
        if overlap_hours(interval_start, end, hour) > VALUE_TOLERANCE
    }
