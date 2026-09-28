"""Deterministic Stage 10 economics artifact pipeline."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .config import (
    ANNUALIZED_OUTPUT,
    ANNUAL_OM_FRACTION,
    AUG_SEP_OUTPUT,
    CAPACITIES_KWP,
    CAPACITY_COMPARISON_OUTPUT,
    DEMAND_ANNUALIZATION_FACTOR,
    EXPORT_COMPENSATION_EUR_PER_KWH,
    FIGURES_DIR,
    INSTALLATION_COST_EUR_PER_KWP,
    REFERENCE_CAPACITY_KWP,
    SUMMARY_OUTPUT,
)
from .data import authoritative_inputs
from .economics import annualize, calculate_observed, wide_comparison
from .figures import COLORS, comparison_panel, line_comparison, production_bars
from .validation import validate


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _calculate() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    observed, baselines = calculate_observed()
    annualized = annualize(observed, baselines)
    return observed, annualized, wide_comparison(annualized)


def _decomposition(annualized: list[dict[str, Any]]) -> dict[str, Any]:
    lookup = {(row["capacity_kwp"], row["behavior"]): row for row in annualized}
    first_current = lookup[(CAPACITIES_KWP[0], "current")]
    first_optimized = lookup[(CAPACITIES_KWP[0], "optimized")]
    behavior_savings = (
        first_current["no_pv_annual_net_electricity_cost_eur"]
        - first_optimized["no_pv_annual_net_electricity_cost_eur"]
    )
    capacities = []
    for capacity in CAPACITIES_KWP:
        current, optimized = lookup[(capacity, "current")], lookup[(capacity, "optimized")]
        combined_gross = (
            current["no_pv_annual_net_electricity_cost_eur"]
            - optimized["annual_net_electricity_cost_eur"]
        )
        capacities.append({
            "capacity_kwp": capacity,
            "behavioral_optimization_effect_no_pv_eur": behavior_savings,
            "pv_effect_current_habits_gross_eur": current["gross_annual_electricity_benefit_eur"],
            "pv_effect_current_habits_net_after_om_eur": current["net_annual_pv_benefit_eur"],
            "pv_effect_optimized_habits_gross_eur": optimized["gross_annual_electricity_benefit_eur"],
            "pv_effect_optimized_habits_net_after_om_eur": optimized["net_annual_pv_benefit_eur"],
            "combined_current_no_pv_to_optimized_pv_gross_eur": combined_gross,
            "combined_current_no_pv_to_optimized_pv_net_after_om_eur": combined_gross - optimized["annual_om_eur"],
            "gross_decomposition_identity_holds": abs(
                combined_gross - behavior_savings - optimized["gross_annual_electricity_benefit_eur"]
            ) <= 1e-8,
        })
    return {
        "label": "ANNUALIZED ESTIMATE",
        "current_no_pv_annual_cost_eur": first_current["no_pv_annual_net_electricity_cost_eur"],
        "optimized_no_pv_annual_cost_eur": first_optimized["no_pv_annual_net_electricity_cost_eur"],
        "behavioral_optimization_effect_no_pv_eur": behavior_savings,
        "by_capacity": capacities,
    }


def _figures(wide: list[dict[str, Any]]) -> None:
    production_bars(FIGURES_DIR / "annual_pv_production_vs_capacity.svg", wide)
    line_comparison(
        FIGURES_DIR / "grid_import_vs_pv_capacity.svg",
        "Annual grid import versus PV capacity",
        wide,
        [("current_annual_grid_imported_kwh", "Current habits", COLORS["current"]),
         ("optimized_annual_grid_imported_kwh", "Optimized habits", COLORS["optimized"])],
        "kWh/year",
    )
    line_comparison(
        FIGURES_DIR / "pv_self_consumption_vs_capacity.svg",
        "Annual PV self-consumed versus capacity",
        wide,
        [("current_annual_pv_self_consumed_kwh", "Current habits", COLORS["current"]),
         ("optimized_annual_pv_self_consumed_kwh", "Optimized habits", COLORS["optimized"])],
        "kWh/year",
    )
    line_comparison(
        FIGURES_DIR / "annual_electricity_cost_vs_capacity.svg",
        "Annual net electricity cost versus capacity",
        wide,
        [("current_annual_net_electricity_cost_eur", "Current habits", COLORS["current"]),
         ("optimized_annual_net_electricity_cost_eur", "Optimized habits", COLORS["optimized"])],
        "EUR/year",
    )
    line_comparison(
        FIGURES_DIR / "simple_payback_vs_capacity.svg",
        "Simple payback versus PV capacity",
        wide,
        [("current_simple_payback_years", "Current habits", COLORS["current"]),
         ("optimized_simple_payback_years", "Optimized habits", COLORS["optimized"])],
        "years",
    )
    reference = next(row for row in wide if row["capacity_kwp"] == REFERENCE_CAPACITY_KWP)
    comparison_panel(FIGURES_DIR / "current_vs_optimized_5kwp.svg", reference)


def run() -> dict[str, Any]:
    observed, annualized, wide = _calculate()
    repeat = _calculate()
    first_payload = {"observed": observed, "annualized": annualized, "wide": wide}
    second_payload = {"observed": repeat[0], "annualized": repeat[1], "wide": repeat[2]}
    first_hash = hashlib.sha256(_canonical(first_payload).encode()).hexdigest()
    second_hash = hashlib.sha256(_canonical(second_payload).encode()).hexdigest()
    deterministic = first_hash == second_hash
    validation = validate(observed, annualized, wide, deterministic)
    if validation["status"] != "PASS":
        raise RuntimeError("STOP: Stage 10 validation failed: " + "; ".join(validation["problems"]))

    inputs = authoritative_inputs()
    summary = {
        "stage": "10 - PV investment and economics",
        "scope": "PV investment only; Stage 11 not started",
        "authoritative_inputs": {
            key: value for key, value in inputs.items() if key != "stage9_summary"
        },
        "assumptions": {
            "capacities_kwp": list(CAPACITIES_KWP),
            "reference_capacity_kwp": REFERENCE_CAPACITY_KWP,
            "capacities_are_comparisons_not_recommendations": True,
            "installation_cost_eur_per_kwp": INSTALLATION_COST_EUR_PER_KWP,
            "annual_om_fraction_of_initial_investment": ANNUAL_OM_FRACTION,
            "export_compensation_eur_per_kwh": EXPORT_COMPENSATION_EUR_PER_KWH,
            "tariff_eur_per_kwh": {
                "00:00-06:00": 0.18, "06:00-17:00": 0.28,
                "17:00-22:00": 0.40, "22:00-24:00": 0.28,
            },
            "discount_rate": None,
            "degradation": None,
            "inflation": None,
            "subsidies_or_tax_benefits": None,
            "financing": None,
            "battery": None,
        },
        "annualization": {
            "label": "ANNUALIZED ESTIMATE",
            "observed_period_days": 61,
            "demand_and_no_pv_cost_factor": DEMAND_ANNUALIZATION_FACTOR,
            "method": "Scale 61-day demand and no-PV cost by 365/61. For each capacity and behavior, preserve the observed hourly PV self-consumption/export and avoided-import-value per PV kWh, then scale those PV-driven quantities by exact frozen annual PV production divided by observed Aug-Sep PV production.",
            "reason": "Uses only observed/frozen demand-PV coincidence and exact Stage 8 annual PV, without fabricating household profiles for missing months.",
            "limitation": "Assumes Aug-Sep demand timing, PV coincidence, and tariff value per PV kWh are representative of the year; it is not measured annual household performance.",
        },
        "observed_aug_sep": observed,
        "annualized_estimates": annualized,
        "comparison_table": wide,
        "effect_decomposition": _decomposition(annualized),
        "determinism": {
            "identical_recalculation": deterministic,
            "calculation_sha256": first_hash,
            "repeat_sha256": second_hash,
        },
        "validation": validation,
    }

    _write_csv(AUG_SEP_OUTPUT, observed)
    _write_csv(ANNUALIZED_OUTPUT, annualized)
    _write_csv(CAPACITY_COMPARISON_OUTPUT, wide)
    _write_json(SUMMARY_OUTPUT, summary)
    _figures(wide)
    return summary


__all__ = ["run"]
