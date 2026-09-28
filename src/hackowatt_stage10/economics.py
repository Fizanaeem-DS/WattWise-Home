"""Observed and annualized Stage 10 PV economics calculations."""

from __future__ import annotations

from typing import Any

from .config import (
    ANNUAL_OM_FRACTION,
    DEMAND_ANNUALIZATION_FACTOR,
    EXPORT_COMPENSATION_EUR_PER_KWH,
    INSTALLATION_COST_EUR_PER_KWP,
)
from .data import account_hour, get_annual_pv_summary, get_pv_generation, read_csv, tariff_eur_per_kwh
from .config import STAGE9_HOURLY


BEHAVIORS = ("current", "optimized")


def _aggregate(loads: list[float], pv_rows: list[dict[str, Any]], timestamps: list[str]) -> dict[str, float]:
    totals = {
        "household_demand_kwh": 0.0,
        "pv_generation_kwh": 0.0,
        "pv_self_consumed_kwh": 0.0,
        "pv_exported_kwh": 0.0,
        "grid_imported_kwh": 0.0,
        "import_cost_eur": 0.0,
        "export_revenue_eur": 0.0,
        "net_electricity_cost_eur": 0.0,
    }
    for load, pv, timestamp in zip(loads, pv_rows, timestamps):
        generation = float(pv["pv_generation_kwh"])
        values = account_hour(load, generation, tariff_eur_per_kwh(timestamp))
        totals["household_demand_kwh"] += load
        totals["pv_generation_kwh"] += generation
        totals["pv_self_consumed_kwh"] += values["self_consumed_pv_kwh"]
        totals["pv_exported_kwh"] += values["exported_pv_kwh"]
        totals["grid_imported_kwh"] += values["grid_import_kwh"]
        totals["import_cost_eur"] += values["import_cost_eur"]
        totals["export_revenue_eur"] += values["export_revenue_eur"]
        totals["net_electricity_cost_eur"] += values["net_cost_eur"]
    generation = totals["pv_generation_kwh"]
    demand = totals["household_demand_kwh"]
    totals["pv_self_consumption_rate"] = totals["pv_self_consumed_kwh"] / generation if generation else 0.0
    totals["household_solar_coverage_rate"] = totals["pv_self_consumed_kwh"] / demand if demand else 0.0
    return totals


def calculate_observed() -> tuple[list[dict[str, Any]], dict[str, dict[str, float]]]:
    stage9 = read_csv(STAGE9_HOURLY)
    timestamps = [row["timestamp"] for row in stage9]
    loads = {
        behavior: [float(row[f"{behavior}_load_kwh"]) for row in stage9]
        for behavior in BEHAVIORS
    }
    no_pv_rows = [{"pv_generation_kwh": 0.0} for _ in stage9]
    baselines = {behavior: _aggregate(loads[behavior], no_pv_rows, timestamps) for behavior in BEHAVIORS}
    rows: list[dict[str, Any]] = []
    from .config import CAPACITIES_KWP
    for capacity in CAPACITIES_KWP:
        pv = get_pv_generation(capacity)
        for behavior in BEHAVIORS:
            values = _aggregate(loads[behavior], pv, timestamps)
            baseline = baselines[behavior]
            gross = baseline["net_electricity_cost_eur"] - values["net_electricity_cost_eur"]
            rows.append({
                "provenance_label": "OBSERVED/FROZEN AUG-SEP",
                "period_start": timestamps[0],
                "period_end": timestamps[-1],
                "observed_days": 61,
                "capacity_kwp": capacity,
                "behavior": behavior,
                **values,
                "no_pv_grid_imported_kwh": baseline["grid_imported_kwh"],
                "grid_purchase_reduction_kwh": baseline["grid_imported_kwh"] - values["grid_imported_kwh"],
                "no_pv_net_electricity_cost_eur": baseline["net_electricity_cost_eur"],
                "gross_electricity_benefit_eur": gross,
            })
    return rows, baselines


def annualize(observed: list[dict[str, Any]], baselines: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in observed:
        behavior = item["behavior"]
        capacity = float(item["capacity_kwp"])
        annual_pv = float(get_annual_pv_summary(capacity)["annual_generation_kwh"])
        pv_factor = annual_pv / float(item["pv_generation_kwh"])
        demand = baselines[behavior]["household_demand_kwh"] * DEMAND_ANNUALIZATION_FACTOR
        no_pv_grid = demand
        no_pv_cost = baselines[behavior]["net_electricity_cost_eur"] * DEMAND_ANNUALIZATION_FACTOR
        self_consumed = float(item["pv_self_consumed_kwh"]) * pv_factor
        exported = float(item["pv_exported_kwh"]) * pv_factor
        grid_import = demand - self_consumed
        avoided_import_cost = (
            baselines[behavior]["import_cost_eur"] - float(item["import_cost_eur"])
        ) * pv_factor
        import_cost = no_pv_cost - avoided_import_cost
        export_revenue = exported * EXPORT_COMPENSATION_EUR_PER_KWH
        net_cost = import_cost - export_revenue
        gross_benefit = no_pv_cost - net_cost
        investment = capacity * INSTALLATION_COST_EUR_PER_KWP
        annual_om = investment * ANNUAL_OM_FRACTION
        net_benefit = gross_benefit - annual_om
        rows.append({
            "provenance_label": "ANNUALIZED ESTIMATE",
            "annualization_method": "61-day demand/no-PV cost scaled by 365/61; PV-driven flows and value scaled by exact annual PV divided by observed PV",
            "capacity_kwp": capacity,
            "behavior": behavior,
            "annual_pv_production_kwh": annual_pv,
            "annual_household_demand_kwh": demand,
            "annual_pv_self_consumed_kwh": self_consumed,
            "annual_pv_exported_kwh": exported,
            "annual_grid_imported_kwh": grid_import,
            "pv_self_consumption_rate": self_consumed / annual_pv,
            "household_solar_coverage_rate": self_consumed / demand,
            "no_pv_annual_grid_imported_kwh": no_pv_grid,
            "grid_purchase_reduction_kwh": no_pv_grid - grid_import,
            "grid_purchase_reduction_rate": (no_pv_grid - grid_import) / no_pv_grid,
            "annual_import_cost_eur": import_cost,
            "annual_export_revenue_eur": export_revenue,
            "annual_net_electricity_cost_eur": net_cost,
            "no_pv_annual_net_electricity_cost_eur": no_pv_cost,
            "initial_investment_eur": investment,
            "annual_om_eur": annual_om,
            "gross_annual_electricity_benefit_eur": gross_benefit,
            "net_annual_pv_benefit_eur": net_benefit,
            "simple_payback_years": investment / net_benefit if net_benefit > 0 else None,
        })
    return rows


def wide_comparison(annualized: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {(row["capacity_kwp"], row["behavior"]): row for row in annualized}
    rows = []
    for capacity in sorted({row["capacity_kwp"] for row in annualized}):
        current, optimized = by_key[(capacity, "current")], by_key[(capacity, "optimized")]
        row: dict[str, Any] = {
            "provenance_label": "ANNUALIZED ESTIMATE",
            "capacity_kwp": capacity,
            "annual_pv_production_kwh": current["annual_pv_production_kwh"],
            "initial_investment_eur": current["initial_investment_eur"],
            "annual_om_eur": current["annual_om_eur"],
        }
        fields = (
            "annual_household_demand_kwh", "annual_pv_self_consumed_kwh", "annual_pv_exported_kwh",
            "annual_grid_imported_kwh", "pv_self_consumption_rate", "household_solar_coverage_rate",
            "annual_import_cost_eur", "annual_export_revenue_eur", "annual_net_electricity_cost_eur",
            "gross_annual_electricity_benefit_eur", "net_annual_pv_benefit_eur", "simple_payback_years",
        )
        for behavior, values in (("current", current), ("optimized", optimized)):
            for field in fields:
                row[f"{behavior}_{field}"] = values[field]
        row.update({
            "optimization_change_pv_self_consumed_kwh": optimized["annual_pv_self_consumed_kwh"] - current["annual_pv_self_consumed_kwh"],
            "optimization_change_grid_imported_kwh": optimized["annual_grid_imported_kwh"] - current["annual_grid_imported_kwh"],
            "optimization_change_pv_exported_kwh": optimized["annual_pv_exported_kwh"] - current["annual_pv_exported_kwh"],
            "optimization_change_annual_net_electricity_cost_eur": optimized["annual_net_electricity_cost_eur"] - current["annual_net_electricity_cost_eur"],
            "optimization_change_net_annual_pv_benefit_eur": optimized["net_annual_pv_benefit_eur"] - current["net_annual_pv_benefit_eur"],
            "optimization_change_simple_payback_years": optimized["simple_payback_years"] - current["simple_payback_years"],
        })
        rows.append(row)
    return rows


__all__ = ["BEHAVIORS", "annualize", "calculate_observed", "wide_comparison"]
