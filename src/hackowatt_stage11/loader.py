"""Fail-closed loaders from frozen backend artifacts to the app contract."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    ComponentLoad,
    FlexibilityClass,
    FlexibilityItem,
    ForecastBundle,
    ForecastHourPoint,
    HistoricalHourPoint,
    Horizon,
    LoadComponent,
    OptimizationBundle,
    OptimizationHourPoint,
    PVEconomicsRow,
    PVBundle,
    Provenance,
    ShiftedEvent,
    TIMEZONE,
    WattWiseData,
)

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"

HISTORY_PATH = PROCESSED / "stage3c_household_hourly.csv"
FORECAST_PATH = PROCESSED / "stage6b_forecast_explained.csv"
STAGE6A_PATH = PROCESSED / "stage6a_peak_risk_hourly.csv"
FLEXIBILITY_PATH = ROOT / "stage7" / "artifacts" / "stage7b_optimization_requirements.json"
OPTIMIZATION_HOURLY_PATH = PROCESSED / "stage9_hourly_current_vs_optimized.csv"
OPTIMIZATION_EVENTS_PATH = PROCESSED / "stage9_event_schedule.csv"
OPTIMIZATION_SUMMARY_PATH = PROCESSED / "stage9_optimizer_summary.json"
PV_COMPARISON_PATH = PROCESSED / "stage10_capacity_comparison.csv"
PV_SUMMARY_PATH = PROCESSED / "stage10_economics_summary.json"

COMPONENT_COLUMNS = {
    LoadComponent.HVAC: "hvac_kwh",
    LoadComponent.FRIDGE_FREEZER: "refrigerator_kwh",
    LoadComponent.POOL_CIRCULATION: "pool_circulation_kwh",
    LoadComponent.POOL_HEATING: "pool_heating_kwh",
    LoadComponent.SAUNA: "sauna_kwh",
    LoadComponent.EV1: "ev1_charging_kwh",
    LoadComponent.EV2: "ev2_charging_kwh",
    LoadComponent.COOKING: "cooking_kwh",
    LoadComponent.DISHWASHER: "dishwasher_kwh",
    LoadComponent.WASHER: "washer_kwh",
    LoadComponent.DRYER: "dryer_kwh",
    LoadComponent.TV_COMPUTER: "electronics_kwh",
    LoadComponent.LIGHTING_INTERIOR: "interior_lighting_kwh",
    LoadComponent.LIGHTING_EXTERIOR: "exterior_security_lighting_kwh",
    LoadComponent.SMART_HOME_BASE: "smart_home_base_kwh",
    LoadComponent.PHONE_TABLET: "phone_tablet_kwh",
}


def _require(paths: tuple[Path, ...]) -> None:
    missing = [str(path.relative_to(ROOT)) for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError("Required REAL Stage 11 source artifact(s) missing: " + ", ".join(missing))


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _real(*artifacts: Path) -> Provenance:
    return Provenance("real", tuple(path.relative_to(ROOT).as_posix() for path in artifacts))


def _iso(timestamp: str) -> str:
    parsed = datetime.fromisoformat(timestamp)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp is not timezone-aware: {timestamp}")
    return parsed.isoformat()


def _history() -> tuple[HistoricalHourPoint, ...]:
    points: list[HistoricalHourPoint] = []
    for row in _rows(HISTORY_PATH):
        components = tuple(
            ComponentLoad(component, float(row[column]))
            for component, column in COMPONENT_COLUMNS.items()
        )
        total = float(row["household_total_kwh"])
        if abs(sum(item.kwh for item in components) - total) > 1e-7:
            raise ValueError(f"Stage 3C components do not reconcile at {row['timestamp']}")
        points.append(HistoricalHourPoint(
            timestamp=_iso(row["timestamp"]),
            total_kwh=total,
            outdoor_temp_c=float(row["temperature_2m"]),
            indoor_temp_c=float(row["indoor_temperature_c"]),
            occupancy_state=row["occupancy_state"],
            is_away=row["away"] == "True",
            components=components,
        ))
    if len(points) != 1464:
        raise ValueError(f"Stage 3C expected 1464 hours, found {len(points)}")
    return tuple(points)


def _forecasts() -> dict[Horizon, ForecastBundle]:
    rows = _rows(FORECAST_PATH)
    bundles: dict[Horizon, ForecastBundle] = {}
    for horizon in Horizon:
        candidates: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            if int(row["horizon_hours"]) == horizon.hours:
                candidates[row["forecast_origin"]].append(row)
        complete = {
            origin: sorted(group, key=lambda item: int(item["lead_hour"]))
            for origin, group in candidates.items()
            if len(group) == horizon.hours
            and {int(item["lead_hour"]) for item in group} == set(range(1, horizon.hours + 1))
        }
        if not complete:
            raise RuntimeError(f"No complete REAL {horizon.value} Stage 6B forecast is available")
        origin = max(complete, key=datetime.fromisoformat)
        points = tuple(ForecastHourPoint(
            timestamp=_iso(row["timestamp"]),
            lead_hour=int(row["lead_hour"]),
            expected_kwh=float(row["point_forecast_kwh"]),
            p10_kwh=float(row["p10_kwh"]),
            p50_kwh=float(row["p50_kwh"]),
            p90_kwh=float(row["p90_kwh"]),
            p95_kwh=float(row["p95_kwh"]),
            outdoor_temp_c=float(row["temperature_2m"]),
            peak_probability=float(row["peak_probability"]),
            peak_risk_label=row["peak_risk_label"],
            tariff_eur_per_kwh=float(row["tariff_eur_per_kwh"]),
            tariff_period=row["tariff_period"],
            primary_explanation=row["primary_explanation"],
            secondary_explanation=row["secondary_explanation"],
        ) for row in complete[origin])
        bundles[horizon] = ForecastBundle(
            horizon=horizon,
            forecast_origin=_iso(origin),
            points=points,
            total_expected_kwh=sum(point.expected_kwh for point in points),
            provenance=_real(FORECAST_PATH, STAGE6A_PATH),
        )
    return bundles


def _flexibility() -> tuple[FlexibilityItem, ...]:
    data = _json(FLEXIBILITY_PATH)
    if data.get("source") != "real" or data.get("mock_generator_used") is not False:
        raise ValueError("Stage 7B production requirements are not marked REAL")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in data["events"]:
        if event.get("source") != "real":
            raise ValueError(f"Stage 7 event {event.get('event_id')} is not REAL")
        grouped[event["component"]].append(event)
    items: list[FlexibilityItem] = []
    for rule in data["static_rules"]:
        events = grouped.get(rule["component"], [])
        energies = [float(event["energy_kwh"]) for event in events]
        durations = [float(event["duration_hours"]) for event in events]
        items.append(FlexibilityItem(
            component=LoadComponent(rule["component"]),
            flexibility_class=FlexibilityClass(rule["flexibility_class"]),
            notes=rule.get("notes", ""),
            earliest_start=rule.get("earliest_start"),
            latest_start=rule.get("latest_start"),
            latest_completion=rule.get("latest_completion"),
            comfort_band_min=rule.get("comfort_band_min"),
            comfort_band_max=rule.get("comfort_band_max"),
            actual_event_count=len(events),
            actual_energy_min_kwh=min(energies) if energies else None,
            actual_energy_max_kwh=max(energies) if energies else None,
            actual_duration_min_hours=min(durations) if durations else None,
            actual_duration_max_hours=max(durations) if durations else None,
        ))
    return tuple(items)


def _optimization() -> OptimizationBundle:
    hourly = tuple(OptimizationHourPoint(
        timestamp=_iso(row["timestamp"]),
        current_load_kwh=float(row["current_load_kwh"]),
        optimized_load_kwh=float(row["optimized_load_kwh"]),
        pv_generation_kwh=float(row["pv_generation_kwh"]),
        tariff_eur_per_kwh=float(row["tariff_eur_per_kwh"]),
        current_grid_import_kwh=float(row["current_grid_import_kwh"]),
        optimized_grid_import_kwh=float(row["optimized_grid_import_kwh"]),
        current_self_consumed_pv_kwh=float(row["current_self_consumed_pv_kwh"]),
        optimized_self_consumed_pv_kwh=float(row["optimized_self_consumed_pv_kwh"]),
        current_exported_pv_kwh=float(row["current_exported_pv_kwh"]),
        optimized_exported_pv_kwh=float(row["optimized_exported_pv_kwh"]),
        current_net_cost_eur=float(row["current_net_cost_eur"]),
        optimized_net_cost_eur=float(row["optimized_net_cost_eur"]),
    ) for row in _rows(OPTIMIZATION_HOURLY_PATH))
    if len(hourly) != 1464:
        raise ValueError(f"Stage 9 expected 1464 hours, found {len(hourly)}")
    shifted: list[ShiftedEvent] = []
    for row in _rows(OPTIMIZATION_EVENTS_PATH):
        shift = float(row["shift_hours"])
        if abs(shift) <= 1e-9:
            continue
        shifted.append(ShiftedEvent(
            event_id=row["event_id"],
            component=LoadComponent(row["component"]),
            original_start=_iso(row["original_start"]),
            optimized_start=_iso(row["optimized_start"]),
            energy_kwh=float(row["energy_kwh"]),
            duration_hours=float(row["duration_hours"]),
            shift_hours=shift,
            constraint_status=row["constraint_status"],
        ))
    return OptimizationBundle(
        hourly=hourly,
        shifted_events=tuple(shifted),
        summary=_json(OPTIMIZATION_SUMMARY_PATH),
        provenance=_real(OPTIMIZATION_HOURLY_PATH, OPTIMIZATION_EVENTS_PATH, OPTIMIZATION_SUMMARY_PATH),
    )


def _prefixed(row: dict[str, str], prefix: str) -> dict[str, float]:
    return {
        key.removeprefix(prefix): float(value)
        for key, value in row.items()
        if key.startswith(prefix) and value != ""
    }


def _pv() -> PVBundle:
    summary = _json(PV_SUMMARY_PATH)
    rows: list[PVEconomicsRow] = []
    for row in _rows(PV_COMPARISON_PATH):
        if row["provenance_label"] != "ANNUALIZED ESTIMATE":
            raise ValueError("Stage 10 annual comparison is not labeled ANNUALIZED ESTIMATE")
        rows.append(PVEconomicsRow(
            capacity_kwp=float(row["capacity_kwp"]),
            annual_pv_production_kwh=float(row["annual_pv_production_kwh"]),
            initial_investment_eur=float(row["initial_investment_eur"]),
            annual_om_eur=float(row["annual_om_eur"]),
            current=_prefixed(row, "current_"),
            optimized=_prefixed(row, "optimized_"),
            optimization_change=_prefixed(row, "optimization_change_"),
        ))
    if {row.capacity_kwp for row in rows} != {3.0, 5.0, 8.0, 10.0}:
        raise ValueError("Stage 10 does not contain exactly the four approved PV capacities")
    annualization = summary["annualization"]
    if annualization.get("label") != "ANNUALIZED ESTIMATE":
        raise ValueError("Stage 10 annualization label is missing")
    return PVBundle(
        rows=tuple(sorted(rows, key=lambda row: row.capacity_kwp)),
        annualization=annualization,
        effect_decomposition=summary["effect_decomposition"],
        provenance=_real(PV_COMPARISON_PATH, PV_SUMMARY_PATH),
    )


def load_real_data() -> WattWiseData:
    """Load every final app section from frozen artifacts or fail clearly."""
    _require((
        HISTORY_PATH, FORECAST_PATH, STAGE6A_PATH, FLEXIBILITY_PATH,
        OPTIMIZATION_HOURLY_PATH, OPTIMIZATION_EVENTS_PATH,
        OPTIMIZATION_SUMMARY_PATH, PV_COMPARISON_PATH, PV_SUMMARY_PATH,
    ))
    data = WattWiseData(
        household_label="Anna & Robert — Barcelona",
        history=_history(),
        history_provenance=_real(HISTORY_PATH),
        forecasts=_forecasts(),
        flexibility=_flexibility(),
        flexibility_provenance=_real(FLEXIBILITY_PATH),
        optimization=_optimization(),
        pv=_pv(),
    )
    if data.has_any_mock():
        raise RuntimeError("Stage 11 refuses to display non-REAL final evidence")
    return data
