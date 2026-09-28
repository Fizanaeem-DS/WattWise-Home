"""Ivana's A/B/C/D Stage 7 rules, with accepted Stage 7B corrections.

Representative point values remain for UI/mock display only.  Production
optimization must use ``build_optimization_requirements`` and actual Stage 3
event quantities.
"""

from __future__ import annotations

from contract.schema import FlexibilityClass as F
from contract.schema import FlexibilityConstraint as C
from contract.schema import LoadComponent as L

_CONSTRAINTS = (
    C(L.FRIDGE_FREEZER, F.FIXED, notes="Continuous; optimizer may not change it."),
    C(L.SMART_HOME_BASE, F.FIXED, notes="Continuous; optimizer may not change it."),
    C(L.LIGHTING_EXTERIOR, F.FIXED, notes="Security/exterior lighting; optimizer may not change it."),
    C(L.COOKING, F.BEHAVIOR_DRIVEN, notes="Morning and dinner cooking; forecast, never reschedule."),
    C(L.TV_COMPUTER, F.BEHAVIOR_DRIVEN, notes="Behavioral session; never reschedule."),
    C(L.PHONE_TABLET, F.BEHAVIOR_DRIVEN, notes="Behavior-driven; never reschedule."),
    C(L.LIGHTING_INTERIOR, F.BEHAVIOR_DRIVEN, notes="Occupancy/darkness driven; never reschedule."),
    C(L.HVAC, F.LIMITED_FLEXIBILITY, comfort_band_min=20.0, comfort_band_max=25.0,
      notes="Display envelope only; production has separate heating/cooling bands."),
    C(L.SAUNA, F.LIMITED_FLEXIBILITY, required_runtime_hours=1.5,
      required_runtime_hours_min=1.0, required_runtime_hours_max=2.0,
      max_power_kw=9.0, earliest_start="18:00", latest_start="22:30",
      notes="Representative runtime only; actual start +/-1h, absolute START window 18:00-22:30."),
    C(L.POOL_HEATING, F.LIMITED_FLEXIBILITY, required_runtime_hours=3.5,
      required_runtime_hours_min=2.0, required_runtime_hours_max=5.0,
      max_power_kw=5.0, earliest_start="08:00", latest_completion="22:00",
      notes="Approved same-day production rule; actual Stage 3 service quantity is authoritative."),
    C(L.EV1, F.SHIFTABLE, max_power_kw=7.4, notes="Actual home interval, energy and next departure are per event."),
    C(L.EV2, F.SHIFTABLE, max_power_kw=7.4, notes="Independent of EV1; actual values are per event."),
    C(L.POOL_CIRCULATION, F.SHIFTABLE, required_runtime_hours=8.0,
      required_runtime_hours_min=6.0, required_runtime_hours_max=10.0,
      max_power_kw=1.2, latest_completion="23:59",
      notes="Representative normal-day runtime only; actual normal/AWAY runtime is authoritative."),
    C(L.DISHWASHER, F.SHIFTABLE, required_energy_kwh=1.0,
      required_energy_kwh_min=0.8, required_energy_kwh_max=1.2,
      latest_completion="06:30", completion_next_day=True,
      notes="No fixed earliest clock time; actual occurrence establishes availability."),
    C(L.WASHER, F.SHIFTABLE, required_energy_kwh=0.8,
      required_energy_kwh_min=0.6, required_energy_kwh_max=1.0,
      required_runtime_hours=1.25, required_runtime_hours_min=1.0,
      required_runtime_hours_max=1.5, latest_completion="23:00",
      notes="No fixed earliest clock time; actual occurrence establishes availability."),
    C(L.DRYER, F.SHIFTABLE, required_energy_kwh=2.0,
      required_energy_kwh_min=1.5, required_energy_kwh_max=2.5,
      required_runtime_hours=1.25, required_runtime_hours_min=1.0,
      required_runtime_hours_max=1.5, latest_completion="23:00",
      notes="Must follow paired washer; actual dependency and quantities are authoritative."),
)


def get_constraints() -> list[C]:
    return list(_CONSTRAINTS)


def get_constraint(component: L) -> C | None:
    return next((item for item in _CONSTRAINTS if item.component == component), None)


def validate_constraints() -> list[str]:
    problems: list[str] = []
    if len({item.component for item in _CONSTRAINTS}) != len(_CONSTRAINTS):
        problems.append("duplicate component")
    missing = set(L) - {item.component for item in _CONSTRAINTS}
    if missing:
        problems.append(f"missing components: {sorted(item.value for item in missing)}")
    sauna = get_constraint(L.SAUNA)
    if sauna is None or sauna.latest_start != "22:30" or sauna.latest_completion is not None:
        problems.append("sauna must use latest START 22:30")
    for component in (L.DISHWASHER, L.WASHER, L.DRYER):
        item = get_constraint(component)
        if item is None or item.earliest_start is not None:
            problems.append(f"{component.value} must not have a static earliest start")
    return problems
