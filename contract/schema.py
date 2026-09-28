"""Ivana's Stage 7 static backend/app contract, integrated for production.

The static values in :class:`FlexibilityConstraint` are policy caps or UI
representatives.  They are never event-instance inputs to an optimizer.  Real
optimizer inputs are defined separately in ``contract.production_schema``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

Source = Literal["mock", "real", "partial"]
TIMEZONE = "Europe/Madrid"
CURRENCY = "EUR"


class LoadComponent(str, Enum):
    HVAC = "hvac"
    FRIDGE_FREEZER = "fridge_freezer"
    POOL_CIRCULATION = "pool_circulation"
    POOL_HEATING = "pool_heating"
    SAUNA = "sauna"
    EV1 = "ev1"
    EV2 = "ev2"
    COOKING = "cooking"
    DISHWASHER = "dishwasher"
    WASHER = "washer"
    DRYER = "dryer"
    TV_COMPUTER = "tv_computer"
    LIGHTING_INTERIOR = "lighting_interior"
    LIGHTING_EXTERIOR = "lighting_exterior"
    SMART_HOME_BASE = "smart_home_base"
    PHONE_TABLET = "phone_tablet"


class FlexibilityClass(str, Enum):
    """The frozen A/B/C/D classification."""

    FIXED = "fixed"  # A
    BEHAVIOR_DRIVEN = "behavior_driven"  # B
    LIMITED_FLEXIBILITY = "limited"  # C
    SHIFTABLE = "shiftable"  # D


@dataclass(frozen=True)
class FlexibilityConstraint:
    """Static component rule/cap imported from Ivana's Stage 7 design.

    ``required_*`` point values are UI/mock representatives only.  When an
    actual Stage 3 event exists, its values are authoritative and must be
    carried in a ``ProductionEventConstraint``.
    """

    component: LoadComponent
    flexibility_class: FlexibilityClass
    required_energy_kwh: float | None = None
    required_energy_kwh_min: float | None = None
    required_energy_kwh_max: float | None = None
    required_runtime_hours: float | None = None
    required_runtime_hours_min: float | None = None
    required_runtime_hours_max: float | None = None
    max_power_kw: float | None = None
    earliest_start: str | None = None
    latest_start: str | None = None
    latest_completion: str | None = None
    completion_next_day: bool = False
    comfort_band_min: float | None = None
    comfort_band_max: float | None = None
    notes: str = ""

