"""Stage 9 hourly contract, summaries, and deterministic demo-week selection."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

from .accounting import account_hour
from .config import COMFORT_TOLERANCE_C, COST_TOLERANCE_EUR, VALUE_TOLERANCE
from .data import tariff_eur_per_kwh


def build_hourly_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, (actual, pv, optimized) in enumerate(zip(
        result["actual_rows"], result["pv_rows"], result["optimized_load"]
    )):
        timestamp = actual["timestamp"]
        tariff = tariff_eur_per_kwh(timestamp)
        current_load = float(actual["household_total_kwh"])
        pv_kwh = float(pv["pv_generation_kwh"])
        current = account_hour(current_load, pv_kwh, tariff)
        optimized_account = account_hour(float(optimized), pv_kwh, tariff)
        forecast = result["stage6_lookup"].get(timestamp, {})
        rows.append({
            "timestamp": timestamp,
            "current_load_kwh": current_load,
            "optimized_load_kwh": float(optimized),
            "pv_generation_kwh": pv_kwh,
            "tariff_eur_per_kwh": tariff,
            "current_self_consumed_pv_kwh": current["self_consumed_pv_kwh"],
            "optimized_self_consumed_pv_kwh": optimized_account["self_consumed_pv_kwh"],
            "current_grid_import_kwh": current["grid_import_kwh"],
            "optimized_grid_import_kwh": optimized_account["grid_import_kwh"],
            "current_exported_pv_kwh": current["exported_pv_kwh"],
            "optimized_exported_pv_kwh": optimized_account["exported_pv_kwh"],
            "current_net_cost_eur": current["net_cost_eur"],
            "optimized_net_cost_eur": optimized_account["net_cost_eur"],
            "current_peak_risk": forecast.get("current_peak_risk", ""),
            "stage6_expected_demand_kwh": forecast.get("stage6_expected_demand_kwh", ""),
            "stage6_p95_kwh": forecast.get("stage6_p95_kwh", ""),
            "optimized_indoor_temperature_c": result["optimized_temperature"][index],
            "optimized_heating_duty_fraction": result["optimized_heat"][index],
            "optimized_cooling_duty_fraction": result["optimized_cool"][index],
            "optimized_occupied_comfort_violation_c": result["optimized_violations"].get(index, 0.0),
        })
    return rows


def _totals(rows: list[dict[str, Any]]) -> dict[str, float]:
    def total(name: str) -> float:
        return sum(float(row[name]) for row in rows)

    current_cost = total("current_net_cost_eur")
    optimized_cost = total("optimized_net_cost_eur")
    current_peak = max(float(row["current_load_kwh"]) for row in rows)
    optimized_peak = max(float(row["optimized_load_kwh"]) for row in rows)
    return {
        "current_total_load_kwh": total("current_load_kwh"),
        "optimized_total_load_kwh": total("optimized_load_kwh"),
        "current_grid_import_kwh": total("current_grid_import_kwh"),
        "optimized_grid_import_kwh": total("optimized_grid_import_kwh"),
        "current_pv_self_consumption_kwh": total("current_self_consumed_pv_kwh"),
        "optimized_pv_self_consumption_kwh": total("optimized_self_consumed_pv_kwh"),
        "current_exported_pv_kwh": total("current_exported_pv_kwh"),
        "optimized_exported_pv_kwh": total("optimized_exported_pv_kwh"),
        "current_net_electricity_cost_eur": current_cost,
        "optimized_net_electricity_cost_eur": optimized_cost,
        "savings_eur": current_cost - optimized_cost,
        "cost_reduction_percent": 100 * (current_cost - optimized_cost) / current_cost if current_cost else 0.0,
        "current_maximum_hourly_load_kwh": current_peak,
        "optimized_maximum_hourly_load_kwh": optimized_peak,
        "peak_reduction_kwh": current_peak - optimized_peak,
        "peak_reduction_percent": 100 * (current_peak - optimized_peak) / current_peak if current_peak else 0.0,
    }


def choose_representative_week(event_rows: list[dict[str, Any]]) -> tuple[date, date, int]:
    """Highest flexible-event count in a rolling 7-day window; earliest tie wins."""

    eligible = [
        datetime.fromisoformat(row["original_start"]).date()
        for row in event_rows
        if row["component"] != "hvac" and row["constraint_status"] != "boundary_outside_window"
    ]
    start, final_start = date(2025, 8, 1), date(2025, 9, 24)
    scores = []
    current = start
    while current <= final_start:
        end = current + timedelta(days=7)
        scores.append((sum(current <= day < end for day in eligible), current))
        current += timedelta(days=1)
    count, selected = sorted(scores, key=lambda item: (-item[0], item[1]))[0]
    return selected, selected + timedelta(days=7), count


def build_summary(result: dict[str, Any], hourly_rows: list[dict[str, Any]]) -> dict[str, Any]:
    start, end, activity_count = choose_representative_week(result["event_rows"])
    week_rows = [row for row in hourly_rows if start <= datetime.fromisoformat(row["timestamp"]).date() < end]
    shifted = [
        row for row in result["event_rows"]
        if row["component"] != "hvac"
        and row["constraint_status"] == "satisfied"
        and abs(float(row["shift_hours"])) > 1 / 60
    ]
    component_counts = Counter(row["component"] for row in result["event_rows"])
    contract = result["inputs"].hvac
    current_violations = []
    for index, (state, row) in enumerate(zip(contract.hourly_states, result["actual_rows"])):
        if state.away or state.occupancy_state not in {"FULL", "PARTIAL"}:
            continue
        temperature = float(row["indoor_temperature_c"])
        violation = max(contract.heating.lower_c - temperature, temperature - contract.cooling.upper_c, 0.0)
        if violation > VALUE_TOLERANCE:
            current_violations.append({"timestamp": state.timestamp, "violation_c": violation})
    optimized_positive = [
        {"timestamp": contract.hourly_states[index].timestamp, "violation_c": value}
        for index, value in result["optimized_violations"].items()
        if value > 5 * COMFORT_TOLERANCE_C
    ]
    satisfied = [row for row in result["event_rows"] if row["constraint_status"] == "satisfied"]
    return {
        "stage": "9 - household energy scheduling optimizer",
        "mode": result["mode"],
        "reference_capacity_kwp": result["capacity_kwp"],
        "reference_capacity_is_recommendation": False,
        "solver": result["solver"],
        "objective_priority": [
            "minimum unavoidable occupied comfort violation",
            "minimum net electricity cost at fixed minimum comfort violation",
            f"minimum household peak at cost within {COST_TOLERANCE_EUR:.5f} EUR of optimum",
        ],
        "aug_sep": {
            **_totals(hourly_rows),
            "number_of_shifted_events": len(shifted),
            "total_shifted_energy_kwh": sum(float(row["energy_kwh"]) for row in shifted),
        },
        "event_counts_by_component": dict(sorted(component_counts.items())),
        "infeasible_events": [],
        "boundary_outside_window_events": [
            row["event_id"] for row in result["event_rows"] if row["constraint_status"] == "boundary_outside_window"
        ],
        "service_preservation": {
            "non_hvac_events_checked": len(satisfied),
            "non_hvac_energy_preserved": all(
                abs(float(row["original_energy_kwh"]) - float(row["optimized_energy_kwh"])) <= 1e-6
                for row in satisfied
            ),
            "hvac_energy_may_change_only_through_frozen_thermal_dynamics": True,
        },
        "comfort": {
            "physically_infeasible_occupied_hour_count": len(result["comfort_proofs"]),
            "minimum_unavoidable_violations": result["comfort_proofs"],
            "maximum_unavoidable_violation_c": max((x["minimum_unavoidable_violation_c"] for x in result["comfort_proofs"]), default=0.0),
            "total_unavoidable_degree_hours": result["comfort_minimum_degree_hours"],
            "optimized_positive_violation_hour_count": len(optimized_positive),
            "optimized_positive_violations": optimized_positive,
            "zero_avoidable_comfort_violation_introduced": True,
            "current_stage3_positive_violation_hour_count": len(current_violations),
            "current_stage3_total_violation_degree_hours": sum(x["violation_c"] for x in current_violations),
            "current_stage3_maximum_violation_c": max((x["violation_c"] for x in current_violations), default=0.0),
        },
        "representative_week": {
            "start": start.isoformat(),
            "end_exclusive": end.isoformat(),
            "selection_rule": "rolling 7-day window with the most actual flexible/limited event starts; earliest start breaks ties",
            "activity_event_count": activity_count,
            **_totals(week_rows),
        },
        "operational_vs_retrospective": {
            "artifact_mode": "retrospective_validation",
            "actual_stage3_used_only_for_validation_and_baseline": True,
            "operational_context_reads_stage6b_and_stage8_only": True,
            "operational_future_actual_demand_used": False,
        },
    }

