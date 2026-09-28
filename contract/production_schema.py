"""Production-only Stage 7 event and HVAC optimizer requirements."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from contract.schema import FlexibilityClass, LoadComponent


@dataclass(frozen=True)
class AvailabilityInterval:
    """A timezone-aware interval in which an event may start or operate."""

    start: str
    end: str | None
    interval_type: str
    source_event_id: str | None = None


@dataclass(frozen=True)
class ProductionEventConstraint:
    """One actual Stage 3 service requirement prepared for Stage 9.

    ``availability_intervals`` are machine-readable feasible-start intervals
    unless ``availability_semantics`` says ``operation``.  Energy, duration,
    power, identity, and dependency fields are copied from frozen ledgers.
    """

    event_id: str
    component: LoadComponent
    flexibility_class: FlexibilityClass
    date: str
    energy_kwh: float
    duration_hours: float
    power_kw: float
    actual_start: str
    actual_end: str
    preferred_start: str | None = None
    feasible_start: str | None = None
    feasible_end: str | None = None
    deadline: str | None = None
    latest_start: str | None = None
    availability_intervals: tuple[AvailabilityInterval, ...] = ()
    availability_semantics: str = "feasible_start"
    away_intervals: tuple[AvailabilityInterval, ...] = ()
    depends_on_event_id: str | None = None
    dependency_delay_hours: float | None = None
    vehicle_id: str | None = None
    next_departure: str | None = None
    max_power_kw: float | None = None
    boundary_truncated: bool | None = None
    delivered_in_window_kwh: float | None = None
    remaining_energy_kwh: float | None = None
    coherent_cycle: bool = True
    same_calendar_day: bool | None = None
    actual_segments: tuple[AvailabilityInterval, ...] = ()
    source: str = "real"
    provenance: str = ""


@dataclass(frozen=True)
class HVACModeConstraint:
    mode: str
    sampled_preference_c: float
    lower_c: float
    upper_c: float
    rated_power_kw: float


@dataclass(frozen=True)
class HVACHourState:
    timestamp: str
    occupancy_state: str
    away: bool
    outdoor_temperature_c: float
    indoor_temperature_c: float
    effective_heating_target_c: float
    effective_cooling_target_c: float
    actual_mode: str


@dataclass(frozen=True)
class HVACProductionConstraint:
    event_id: str
    component: LoadComponent
    flexibility_class: FlexibilityClass
    heating: HVACModeConstraint
    cooling: HVACModeConstraint
    mutually_exclusive: bool
    limited_preconditioning: bool
    no_occupied_comfort_violation: bool
    thermal_time_constant_hours: float
    heating_effect_c_per_hour: float
    cooling_effect_c_per_hour: float
    hysteresis_c: float
    initial_indoor_temperature_c: float
    initial_mode: str
    hourly_states: tuple[HVACHourState, ...]
    source: str = "real"
    provenance: str = ""


@dataclass(frozen=True)
class OptimizationRequirements:
    static_rules: tuple[Any, ...]
    events: tuple[ProductionEventConstraint, ...]
    hvac: HVACProductionConstraint
    source: str = "real"
    mock_generator_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _enum_values(asdict(self))


def _enum_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _enum_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_enum_values(item) for item in value]
    if isinstance(value, (LoadComponent, FlexibilityClass)):
        return value.value
    return value
