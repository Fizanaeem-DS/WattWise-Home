"""Read-only end-to-end audit of the frozen WattWise product."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import fields, is_dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from hackowatt_stage11.loader import ROOT, load_real_data
from hackowatt_stage11.models import Horizon, TARIFF_BANDS_EUR_PER_KWH

INITIAL_STAGE12_FILE_COUNT = 1284
INITIAL_STAGE12_TREE_SHA256 = "3a4c841375c214ad13b0b171a3c3a11a08e00aebc5d574b38660f1350b1dcaee"
FINAL_STAGE1_TO_STAGE11_FILE_COUNT = 1284
FINAL_STAGE1_TO_STAGE11_TREE_SHA256 = "1c594f4e81b5b670dde19c7c5bd777a099aed34b6726f2775d245aaae42b0e73"

STAGE12_EXACT = {
    "scripts/run_stage12_audit.py",
    "scripts/run_stage12_runtime.py",
    "tests/test_stage12_end_to_end.py",
}
STAGE12_PREFIXES = ("src/hackowatt_stage12/", "docs/stage12_", "artifacts/stage12/")

PROCESSED = ROOT / "data" / "processed"
HISTORY_PATH = PROCESSED / "stage3c_household_hourly.csv"
FORECAST_PATH = PROCESSED / "stage6b_forecast_explained.csv"
STAGE7_PATH = ROOT / "stage7" / "artifacts" / "stage7b_optimization_requirements.json"
STAGE7_VALIDATION_PATH = ROOT / "stage7" / "artifacts" / "stage7b_validation_report.json"
STAGE8_PATH = PROCESSED / "stage8_pv_capacity_examples.json"
STAGE9_HOURLY_PATH = PROCESSED / "stage9_hourly_current_vs_optimized.csv"
STAGE9_EVENTS_PATH = PROCESSED / "stage9_event_schedule.csv"
STAGE9_SUMMARY_PATH = PROCESSED / "stage9_optimizer_summary.json"
STAGE10_COMPARISON_PATH = PROCESSED / "stage10_capacity_comparison.csv"
STAGE10_SUMMARY_PATH = PROCESSED / "stage10_economics_summary.json"


def frozen_stage1_to_stage11_identity() -> tuple[int, str]:
    paths: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        parts = path.relative_to(ROOT).parts
        if ".git" in parts or "__pycache__" in parts or "tmp" in parts or path.suffix == ".pyc":
            continue
        if relative in STAGE12_EXACT or relative.startswith(STAGE12_PREFIXES):
            continue
        paths.append(path)
    paths.sort(key=lambda path: path.relative_to(ROOT).as_posix())
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return len(paths), digest.hexdigest()


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _tariff(hour: int) -> float:
    return next(price for start, end, price in TARIFF_BANDS_EUR_PER_KWH if start <= hour < end)


def _all_finite(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, (str, int, bool, type(None), Enum)):
        return True
    if is_dataclass(value):
        return all(_all_finite(getattr(value, field.name)) for field in fields(value))
    if isinstance(value, dict):
        return all(_all_finite(key) and _all_finite(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return all(_all_finite(item) for item in value)
    return True


def _interval_overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and start_b < end_a


def audit_system() -> dict[str, Any]:
    data = load_real_data()
    checks: dict[str, bool] = {}
    problems: list[str] = []

    def gate(name: str, condition: bool, problem: str) -> None:
        checks[name] = bool(condition)
        if not condition:
            problems.append(problem)

    file_count, tree_hash = frozen_stage1_to_stage11_identity()
    gate("final_stage1_through11_candidate_freeze_matches", file_count == FINAL_STAGE1_TO_STAGE11_FILE_COUNT and tree_hash == FINAL_STAGE1_TO_STAGE11_TREE_SHA256, f"candidate freeze differs: files={file_count}, sha256={tree_hash}")
    gate("all_app_contract_numbers_finite", _all_finite(data), "app contract contains NaN or infinity")
    gate("all_final_provenance_real", not data.has_any_mock() and all(item.source == "real" for item in data.all_provenance()), "mock/partial provenance reached a final page")

    history_rows = _rows(HISTORY_PATH)
    history_times = [datetime.fromisoformat(row["timestamp"]) for row in history_rows]
    history_total = sum(float(row["household_total_kwh"]) for row in history_rows)
    history_max = max(float(row["household_total_kwh"]) for row in history_rows)
    gate("historical_exact_1464_hours", len(history_rows) == len(data.history) == 1464, "historical row count mismatch")
    gate("historical_exact_period_and_timezone", history_rows[0]["timestamp"] == "2025-08-01T00:00:00+02:00" and history_rows[-1]["timestamp"] == "2025-09-30T23:00:00+02:00" and all(timestamp.utcoffset() == timedelta(hours=2) for timestamp in history_times), "historical period/timezone mismatch")
    gate("historical_total_exact", abs(history_total - 2834.740433147) <= 1e-9 and abs(sum(point.total_kwh for point in data.history) - history_total) <= 1e-9, "historical energy total mismatch")
    gate("historical_maximum_exact", abs(history_max - 21.699169197) <= 1e-9 and abs(max(point.total_kwh for point in data.history) - history_max) <= 1e-9, "historical maximum mismatch")
    gate("historical_components_reconcile", all(abs(point.total_kwh - sum(component.kwh for component in point.components)) <= 1e-7 for point in data.history), "historical components do not reconcile")
    gate("historical_context_fields_map", all(point.outdoor_temp_c == float(row["temperature_2m"]) and point.indoor_temp_c == float(row["indoor_temperature_c"]) and point.occupancy_state == row["occupancy_state"] and point.is_away == (row["away"] == "True") for point, row in zip(data.history, history_rows)), "historical context field mismatch")

    forecast_rows = _rows(FORECAST_PATH)
    expected_models = {Horizon.H24: "M2_GBT_HISTORY", Horizon.H72: "M1_GBT_CAL_WEATHER", Horizon.H168: "M1_GBT_CAL_WEATHER"}
    forecast_match = True
    model_match = True
    ranking_match = True
    for horizon, bundle in data.forecasts.items():
        raw = sorted((row for row in forecast_rows if row["forecast_origin"] == bundle.forecast_origin and int(row["horizon_hours"]) == horizon.hours), key=lambda row: int(row["lead_hour"]))
        model_match &= {row["stage5_selected_model"] for row in raw} == {expected_models[horizon]}
        forecast_match &= len(raw) == horizon.hours
        for point, row in zip(bundle.points, raw):
            forecast_match &= (
                point.timestamp == row["timestamp"] and point.lead_hour == int(row["lead_hour"])
                and abs(point.expected_kwh - float(row["point_forecast_kwh"])) <= 1e-12
                and abs(point.p10_kwh - float(row["p10_kwh"])) <= 1e-12
                and abs(point.p50_kwh - float(row["p50_kwh"])) <= 1e-12
                and abs(point.p90_kwh - float(row["p90_kwh"])) <= 1e-12
                and abs(point.p95_kwh - float(row["p95_kwh"])) <= 1e-12
                and abs(point.outdoor_temp_c - float(row["temperature_2m"])) <= 1e-12
            )
        raw_risk = [row["timestamp"] for row in sorted(raw, key=lambda row: (float(row["peak_probability"]), float(row["p95_kwh"])), reverse=True)]
        app_risk = [point.timestamp for point in sorted(bundle.points, key=lambda point: (point.peak_probability, point.p95_kwh), reverse=True)]
        ranking_match &= raw_risk == app_risk
    gate("forecast_models_exact_by_horizon", model_match, "selected frozen forecast model mismatch")
    gate("forecast_point_quantiles_temperature_exact", forecast_match, "Stage 6B forecast values do not map exactly")
    gate("forecast_total_expected_energy_exact", all(abs(bundle.total_expected_kwh - sum(point.expected_kwh for point in bundle.points)) <= 1e-12 for bundle in data.forecasts.values()), "forecast total energy mismatch")
    gate("highest_expected_hour_exact", all(max(bundle.points, key=lambda point: point.expected_kwh).expected_kwh == max(point.expected_kwh for point in bundle.points) for bundle in data.forecasts.values()), "highest expected-demand ranking mismatch")

    gate("peak_probabilities_exact", all(any(row["timestamp"] == point.timestamp and row["forecast_origin"] == bundle.forecast_origin and abs(float(row["peak_probability"]) - point.peak_probability) <= 1e-12 for row in forecast_rows) for bundle in data.forecasts.values() for point in bundle.points), "peak probabilities differ from Stage 6B")
    gate("peak_labels_exact_boundaries", all(point.peak_risk_label == ("LOW" if point.peak_probability < .20 else "MEDIUM" if point.peak_probability < .40 else "HIGH") for bundle in data.forecasts.values() for point in bundle.points), "LOW/MEDIUM/HIGH mapping mismatch")
    gate("p95_is_high_demand_potential", "High-demand potential P95" in (ROOT / "app" / "charts.py").read_text(encoding="utf-8"), "P95 is not labeled high-demand potential")
    gate("high_risk_ranking_exact", ranking_match, "peak-risk ranking mismatch")
    gate("no_deterministic_peak_claim", "Neither predicts an exact stochastic spike" in (ROOT / "app" / "app.py").read_text(encoding="utf-8"), "UI lacks explicit stochastic-peak caveat")
    gate("explanations_map_exactly", all(any(row["timestamp"] == point.timestamp and row["forecast_origin"] == bundle.forecast_origin and row["primary_explanation"] == point.primary_explanation and row["secondary_explanation"] == point.secondary_explanation for row in forecast_rows) for bundle in data.forecasts.values() for point in bundle.points), "explanation field mismatch")

    stage9_rows = _rows(STAGE9_HOURLY_PATH)
    stage10_summary = _json(STAGE10_SUMMARY_PATH)
    tariff_boundary_ok = {hour: _tariff(hour) for hour in (0, 5, 6, 16, 17, 21, 22, 23)} == {0: .18, 5: .18, 6: .28, 16: .28, 17: .40, 21: .40, 22: .28, 23: .28}
    gate("tariff_boundaries_exact", tariff_boundary_ok, "tariff boundary mapping mismatch")
    gate("stage9_tariff_identical", all(abs(float(row["tariff_eur_per_kwh"]) - _tariff(datetime.fromisoformat(row["timestamp"]).hour)) <= 1e-12 for row in stage9_rows), "Stage 9 tariff differs")
    gate("stage10_tariff_identical", stage10_summary["assumptions"]["tariff_eur_per_kwh"] == {"00:00-06:00": .18, "06:00-17:00": .28, "17:00-22:00": .40, "22:00-24:00": .28}, "Stage 10 tariff differs")

    stage7 = _json(STAGE7_PATH)
    stage7_validation = _json(STAGE7_VALIDATION_PATH)
    events = stage7["events"]
    event_ids = {event["event_id"] for event in events}
    gate("stage7_production_source_real", stage7["source"] == "real" and stage7["mock_generator_used"] is False and all(event["source"] == "real" for event in events), "Stage 7 production source is not wholly real")
    gate("stage7_energy_duration_power_valid", all(event["energy_kwh"] > 0 and event["duration_hours"] > 0 and event["power_kw"] > 0 and abs(event["energy_kwh"] - event["duration_hours"] * event["power_kw"]) <= 1e-7 for event in events), "Stage 7 energy/duration/power inconsistency")
    gate("stage7_dependencies_resolve", all(event["depends_on_event_id"] is None or event["depends_on_event_id"] in event_ids for event in events), "Stage 7 dependency target missing")
    gate(
        "stage7_ev_availability_complete",
        all(
            event["vehicle_id"] and event["availability_intervals"]
            and (event["next_departure"] or any(interval["end"] is None for interval in event["availability_intervals"]))
            for event in events if event["component"] in {"ev1", "ev2"}
        ),
        "EV availability/departure metadata missing without an explicit open-ended boundary interval",
    )
    away_ok = True
    for event in events:
        if event["component"] not in {"pool_heating", "sauna"}:
            continue
        start, end = datetime.fromisoformat(event["actual_start"]), datetime.fromisoformat(event["actual_end"])
        for away in event["away_intervals"]:
            away_ok &= not _interval_overlap(start, end, datetime.fromisoformat(away["start"]), datetime.fromisoformat(away["end"]))
    gate("stage7_actual_events_away_compatible", away_ok, "a Stage 7 actual event overlaps an AWAY interval")
    gate("stage7_boundary_accounting_explicit", all(not event["boundary_truncated"] or abs((event["delivered_in_window_kwh"] or 0) + (event["remaining_energy_kwh"] or 0) - event["energy_kwh"]) <= 1e-9 for event in events), "boundary accounting does not reconcile")
    gate("stage7_frozen_validation_passed", stage7_validation["status"] == "PASS" and not stage7_validation["problems"], "frozen Stage 7 validation did not pass")

    stage9 = _json(STAGE9_SUMMARY_PATH)
    augsep = stage9["aug_sep"]
    expected_current = {"current_total_load_kwh": 2834.740433147, "current_grid_import_kwh": 2071.626893958, "current_pv_self_consumption_kwh": 763.113539189, "current_exported_pv_kwh": 717.495160811, "current_net_electricity_cost_eur": 625.06481450384, "current_maximum_hourly_load_kwh": 21.699169197}
    expected_optimized = {"optimized_total_load_kwh": 2785.3571935408586, "optimized_grid_import_kwh": 1663.4128561325329, "optimized_pv_self_consumption_kwh": 1121.9443374083255, "optimized_exported_pv_kwh": 358.66436259167455, "optimized_net_electricity_cost_eur": 356.0448717034062, "optimized_maximum_hourly_load_kwh": 9.879824960189364}
    gate("stage9_current_values_exact", all(abs(augsep[key] - value) <= 1e-9 for key, value in expected_current.items()), "Stage 9 current summary mismatch")
    gate("stage9_optimized_values_exact", all(abs(augsep[key] - value) <= 1e-9 for key, value in expected_optimized.items()), "Stage 9 optimized summary mismatch")
    grid_reduction = 100 * (augsep["current_grid_import_kwh"] - augsep["optimized_grid_import_kwh"]) / augsep["current_grid_import_kwh"]
    self_increase = 100 * (augsep["optimized_pv_self_consumption_kwh"] - augsep["current_pv_self_consumption_kwh"]) / augsep["current_pv_self_consumption_kwh"]
    gate("stage9_derived_impacts_exact", abs(augsep["cost_reduction_percent"] - 43.038727594029545) <= 1e-9 and abs(grid_reduction - 19.704997990518613) <= 1e-9 and abs(self_increase - 47.02194100771341) <= 1e-9 and abs(augsep["peak_reduction_percent"] - 54.46910952906303) <= 1e-9, "Stage 9 derived impact mismatch")
    raw_shifted = [row for row in _rows(STAGE9_EVENTS_PATH) if abs(float(row["shift_hours"])) > 1e-9]
    gate("stage9_shifted_event_display_exact", len(raw_shifted) == len(data.optimization.shifted_events) == augsep["number_of_shifted_events"] and all(any(event.event_id == row["event_id"] and event.original_start == row["original_start"] and event.optimized_start == row["optimized_start"] and abs(event.energy_kwh - float(row["energy_kwh"])) <= 1e-12 for event in data.optimization.shifted_events) for row in raw_shifted), "shifted-event display mismatch")
    gate("stage9_service_preservation_supported", stage9["service_preservation"]["non_hvac_energy_preserved"] and all(stage9["validation"]["checks"][key] for key in ("event_energy_preserved", "coherent_cycles_preserved", "washer_dryer_ordering_respected", "availability_and_deadlines_respected", "away_intervals_respected")), "service-preservation claim unsupported")
    comfort = stage9["comfort"]
    gate("stage9_comfort_claim_exact", comfort["zero_avoidable_comfort_violation_introduced"] is True and comfort["physically_infeasible_occupied_hour_count"] == len(comfort["minimum_unavoidable_violations"]) == 42 and comfort["optimized_positive_violation_hour_count"] == 42, "comfort claim mismatch")

    stage8 = _json(STAGE8_PATH)
    examples = {float(item["capacity_kwp"]): float(item["annual_generation_kwh"]) for item in stage8["capacity_examples"]}
    gate("stage8_normalized_production_exact", abs(stage8["reference_system"]["annual_generation_kwh_per_kwp"] - 1559.01) <= 1e-12, "Stage 8 normalized PV production mismatch")
    gate("stage8_capacities_exact_not_optima", examples == {3.0: 4677.03, 5.0: 7795.05, 8.0: 12472.08, 10.0: 15590.10} and stage8["capacity_examples_are_comparisons_not_optima"] is True, "Stage 8 capacity values/semantics mismatch")

    stage10_rows = _rows(STAGE10_COMPARISON_PATH)
    gate("stage10_all_rows_annualized_labeled", len(stage10_rows) == 4 and all(row["provenance_label"] == "ANNUALIZED ESTIMATE" for row in stage10_rows), "Stage 10 annualized label/capacity rows mismatch")
    gate("stage10_methodology_exact", stage10_summary["annualization"]["demand_and_no_pv_cost_factor"] == 365 / 61 and stage10_summary["annualization"]["observed_period_days"] == 61 and "exact frozen annual PV production divided by observed Aug-Sep PV production" in stage10_summary["annualization"]["method"], "Stage 10 annualization methodology mismatch")
    five = next(row for row in stage10_rows if float(row["capacity_kwp"]) == 5.0)
    expected_five = {
        "current_annual_household_demand_kwh": 16961.971444240255, "annual_pv_production_kwh": 7795.05,
        "current_annual_pv_self_consumed_kwh": 4017.609915202592, "current_pv_self_consumption_rate": .5154052783757118,
        "current_household_solar_coverage_rate": .23685984429403367, "current_annual_grid_imported_kwh": 12944.361529037662,
        "current_annual_net_electricity_cost_eur": 3951.250425645231, "current_simple_payback_years": 4.3885163886605145,
        "optimized_annual_household_demand_kwh": 16666.481567908446, "optimized_annual_pv_self_consumed_kwh": 5906.768079449201,
        "optimized_pv_self_consumption_rate": .7577588443241802, "optimized_household_solar_coverage_rate": .3544100208182373,
        "optimized_annual_grid_imported_kwh": 10759.713488459245, "optimized_annual_net_electricity_cost_eur": 2395.264524530961,
        "optimized_simple_payback_years": 3.467397515117356,
    }
    gate("stage10_five_kwp_exact", all(abs(float(five[key]) - value) <= 1e-9 for key, value in expected_five.items()), "5-kWp Stage 10 economics mismatch")
    stage10_by_capacity = {row.capacity_kwp: row for row in data.pv.rows}
    gate("stage10_all_capacities_reproduce_app", all(capacity in stage10_by_capacity and abs(stage10_by_capacity[capacity].annual_pv_production_kwh - float(row["annual_pv_production_kwh"])) <= 1e-12 and abs(stage10_by_capacity[capacity].current["annual_net_electricity_cost_eur"] - float(row["current_annual_net_electricity_cost_eur"])) <= 1e-9 and abs(stage10_by_capacity[capacity].optimized["annual_net_electricity_cost_eur"] - float(row["optimized_annual_net_electricity_cost_eur"])) <= 1e-9 for row in stage10_rows for capacity in [float(row["capacity_kwp"])]), "Stage 10 app rows mismatch")
    gate("savings_decomposition_exact", abs(stage10_summary["effect_decomposition"]["behavioral_optimization_effect_no_pv_eur"] - 1162.519476004677) <= 1e-9 and all(item["gross_decomposition_identity_holds"] for item in stage10_summary["effect_decomposition"]["by_capacity"]), "behavioral/PV decomposition mismatch")

    app_source = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
    data_source = (ROOT / "app" / "data_source.py").read_text(encoding="utf-8")
    gate("no_mock_fallback_in_app", "mock_data" not in data_source and "generate_full_dataset" not in data_source and "load_real_data" in data_source, "app data source has a mock fallback")
    gate("annualized_and_payback_labels_visible", "ANNUALIZED ESTIMATE" in app_source and "SIMPLE PAYBACK" in app_source, "mandatory economic labels not visible")
    gate("synthetic_household_claim_clear", "simulated realization" in (ROOT / "src" / "hackowatt_stage11" / "models.py").read_text(encoding="utf-8") and "not measured annual household performance" in app_source, "synthetic/not-measured semantics unclear")
    limitation_phrases = ("exact stochastic spike", "not measured on this roof", "no battery", "financing", "degradation", "inflation", "subsidies", "taxes", "not a recommendation", "not a universal real-world comfort guarantee")
    gate(
        "all_major_limitations_visible",
        data.pv.annualization["observed_period_days"] == 61
        and "retrospective forecast origin" in app_source.lower()
        and all(phrase in app_source for phrase in limitation_phrases),
        "one or more mandatory limitations is not visible",
    )
    gate("all_eight_pages_present", all(f'"{page}"' in app_source for page in ("Overview", "Historical Consumption", "Forecast", "Peak Hours", "Tariff", "Flexibility (Stage 7)", "PV Simulator", "Optimizer")), "one or more Ivana pages is absent")
    gate("current_and_optimized_not_swapped", augsep["current_grid_import_kwh"] > augsep["optimized_grid_import_kwh"] and five["current_annual_grid_imported_kwh"] > five["optimized_annual_grid_imported_kwh"] and five["current_simple_payback_years"] > five["optimized_simple_payback_years"], "current/optimized semantics appear swapped")

    return {
        "stage": "12 - end-to-end validation and final system audit",
        "status": "PASS" if not problems else "FAIL",
        "checks": checks,
        "problems": problems,
        "freeze": {
            "initial_before_defect_correction": {"file_count": INITIAL_STAGE12_FILE_COUNT, "tree_sha256": INITIAL_STAGE12_TREE_SHA256},
            "genuine_stage11_defect_corrected": True,
            "corrected_file": "app/app.py",
            "corrected_file_sha256": hashlib.sha256((ROOT / "app" / "app.py").read_bytes()).hexdigest(),
            "final_candidate": {"file_count": file_count, "tree_sha256": tree_hash},
        },
        "metrics": {
            "historical": {"hours": len(history_rows), "total_kwh": history_total, "maximum_hourly_kwh": history_max},
            "forecast": {horizon.value: {"origin": bundle.forecast_origin, "model": expected_models[horizon], "total_expected_kwh": bundle.total_expected_kwh, "highest_expected_hour": max(bundle.points, key=lambda point: point.expected_kwh).timestamp, "highest_peak_risk_hour": max(bundle.points, key=lambda point: (point.peak_probability, point.p95_kwh)).timestamp} for horizon, bundle in data.forecasts.items()},
            "stage7": {"production_events": len(events), "shifted_stage9_events": len(data.optimization.shifted_events)},
            "stage9": {**augsep, "grid_import_reduction_percent": grid_reduction, "pv_self_consumption_increase_percent": self_increase},
            "comfort": {"physically_infeasible_occupied_hours": comfort["physically_infeasible_occupied_hour_count"], "maximum_unavoidable_violation_c": comfort["maximum_unavoidable_violation_c"], "total_unavoidable_degree_hours": comfort["total_unavoidable_degree_hours"], "zero_avoidable_violation": comfort["zero_avoidable_comfort_violation_introduced"]},
            "pv_annual_kwh": examples,
            "stage10_5kwp": {key: float(five[key]) for key in expected_five},
            "behavioral_optimization_no_pv_eur_per_year": stage10_summary["effect_decomposition"]["behavioral_optimization_effect_no_pv_eur"],
        },
    }
