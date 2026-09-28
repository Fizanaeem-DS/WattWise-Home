"""Independent Stage 11 integration gates; no upstream artifact is written."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .loader import ROOT, load_real_data
from .models import Horizon, LoadComponent, TARIFF_BANDS_EUR_PER_KWH

FROZEN_STAGE1_TO_STAGE10_FILE_COUNT = 1269
FROZEN_STAGE1_TO_STAGE10_TREE_SHA256 = "0c559f7add82377fe2040bddd34ae4fb8798bea2aeb94f3daf876dc800b07a43"

STAGE11_EXACT_PATHS = {
    "requirements-stage11.txt",
    "tests/test_stage11_app_integration.py",
    "docs/stage11_integration_audit.md",
    "scripts/run_stage11_validation.py",
}
STAGE11_PREFIXES = ("app/", "src/hackowatt_stage11/", "artifacts/stage11/")


def frozen_upstream_identity() -> tuple[int, str]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        parts = path.relative_to(ROOT).parts
        if ".git" in parts or "__pycache__" in parts or "tmp" in parts or path.suffix == ".pyc":
            continue
        if relative in STAGE11_EXACT_PATHS or relative.startswith(STAGE11_PREFIXES):
            continue
        files.append(path)
    files.sort(key=lambda path: path.relative_to(ROOT).as_posix())
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return len(files), digest.hexdigest()


def _tariff(hour: int) -> float:
    return next(price for start, end, price in TARIFF_BANDS_EUR_PER_KWH if start <= hour < end)


def validate() -> dict[str, Any]:
    data = load_real_data()
    checks: dict[str, bool] = {}
    problems: list[str] = []

    def gate(name: str, condition: bool, problem: str) -> None:
        checks[name] = bool(condition)
        if not condition:
            problems.append(problem)

    count, tree_hash = frozen_upstream_identity()
    gate(
        "frozen_stages1_through10_byte_identical",
        count == FROZEN_STAGE1_TO_STAGE10_FILE_COUNT and tree_hash == FROZEN_STAGE1_TO_STAGE10_TREE_SHA256,
        f"frozen tree mismatch: files={count}, sha256={tree_hash}",
    )
    gate("all_required_real_artifacts_load", bool(data.history and data.forecasts and data.flexibility and data.optimization.hourly and data.pv.rows), "one or more final sections are empty")
    gate("no_mock_or_partial_provenance", not data.has_any_mock() and all(item.source == "real" for item in data.all_provenance()), "final page provenance is not wholly REAL")

    history_times = [datetime.fromisoformat(point.timestamp) for point in data.history]
    gate("history_exact_hourly_timeline", len(history_times) == 1464 and len(set(history_times)) == 1464 and all(right - left == timedelta(hours=1) for left, right in zip(history_times, history_times[1:])), "Stage 3C history timeline is not exact hourly")
    gate("history_components_reconcile_kwh", all(abs(point.total_kwh - sum(component.kwh for component in point.components)) <= 1e-7 for point in data.history), "historical component kWh does not reconcile")
    gate("history_timestamps_timezone_aware", all(timestamp.tzinfo is not None and timestamp.utcoffset() is not None for timestamp in history_times), "historical timestamps are naive")

    gate("forecast_horizons_map_exactly", set(data.forecasts) == set(Horizon) and all(len(data.forecasts[horizon].points) == horizon.hours for horizon in Horizon), "24/72/168-hour mapping is incorrect")
    gate("forecast_lead_semantics_exact", all([point.lead_hour for point in data.forecasts[horizon].points] == list(range(1, horizon.hours + 1)) for horizon in Horizon), "forecast leads are not one-based complete horizons")
    gate("forecast_expected_and_quantiles_are_distinct_fields", all(point.expected_kwh >= 0 and point.p10_kwh <= point.p90_kwh <= point.p95_kwh for bundle in data.forecasts.values() for point in bundle.points), "forecast/quantile contract is invalid")
    gate("peak_probabilities_and_labels_exact", all(0 <= point.peak_probability <= 1 and point.peak_risk_label == ("LOW" if point.peak_probability < .20 else "MEDIUM" if point.peak_probability < .40 else "HIGH") for bundle in data.forecasts.values() for point in bundle.points), "Stage 6B probability/label mapping is incorrect")
    gate("deterministic_explanations_present", all(point.primary_explanation.strip() for bundle in data.forecasts.values() for point in bundle.points), "Stage 6B primary explanation is missing")
    gate("official_tariff_exact", all(abs(point.tariff_eur_per_kwh - _tariff(datetime.fromisoformat(point.timestamp).hour)) <= 1e-12 for bundle in data.forecasts.values() for point in bundle.points), "a forecast row uses a non-official tariff")

    expected_classes = {
        "fixed": {LoadComponent.FRIDGE_FREEZER, LoadComponent.SMART_HOME_BASE, LoadComponent.LIGHTING_EXTERIOR},
        "behavior_driven": {LoadComponent.COOKING, LoadComponent.TV_COMPUTER, LoadComponent.PHONE_TABLET, LoadComponent.LIGHTING_INTERIOR},
        "limited": {LoadComponent.HVAC, LoadComponent.SAUNA, LoadComponent.POOL_HEATING},
        "shiftable": {LoadComponent.EV1, LoadComponent.EV2, LoadComponent.POOL_CIRCULATION, LoadComponent.DISHWASHER, LoadComponent.WASHER, LoadComponent.DRYER},
    }
    actual_classes = {key: {item.component for item in data.flexibility if item.flexibility_class.value == key} for key in expected_classes}
    gate("flexibility_abcd_classification_exact", actual_classes == expected_classes, "Stage 7 A/B/C/D classification mismatch")
    gate("actual_event_instances_not_mock_midpoints", all(item.actual_event_count == 0 or item.actual_energy_min_kwh is not None and item.actual_duration_min_hours is not None for item in data.flexibility), "real Stage 7 event-instance ranges are absent")

    stage9 = data.optimization.summary["aug_sep"]
    hourly = data.optimization.hourly
    stage9_reproduced = (
        abs(sum(point.current_load_kwh for point in hourly) - stage9["current_total_load_kwh"]) <= 1e-6
        and abs(sum(point.optimized_load_kwh for point in hourly) - stage9["optimized_total_load_kwh"]) <= 1e-6
        and abs(sum(point.current_grid_import_kwh for point in hourly) - stage9["current_grid_import_kwh"]) <= 1e-6
        and abs(sum(point.optimized_grid_import_kwh for point in hourly) - stage9["optimized_grid_import_kwh"]) <= 1e-6
        and abs(sum(point.current_net_cost_eur for point in hourly) - stage9["current_net_electricity_cost_eur"]) <= 1e-6
        and abs(sum(point.optimized_net_cost_eur for point in hourly) - stage9["optimized_net_electricity_cost_eur"]) <= 1e-6
    )
    gate("stage9_metrics_reproduce_frozen_values", stage9_reproduced, "Stage 9 UI metrics do not reproduce the frozen summary")
    gate("stage9_shifted_events_are_real_and_satisfied", len(data.optimization.shifted_events) == stage9["number_of_shifted_events"] and all(event.constraint_status == "satisfied" for event in data.optimization.shifted_events), "Stage 9 shifted-event contract mismatch")

    summary_rows = {float(row["capacity_kwp"]): row for row in data.pv.effect_decomposition["by_capacity"]}
    gate("all_four_pv_capacities_exact", {row.capacity_kwp for row in data.pv.rows} == {3.0, 5.0, 8.0, 10.0}, "approved PV capacity set mismatch")
    gate("stage10_economics_reproduce_frozen_values", all(abs(row.optimized["net_annual_pv_benefit_eur"] - float(summary_rows[row.capacity_kwp]["pv_effect_optimized_habits_net_after_om_eur"])) <= 1e-9 for row in data.pv.rows), "Stage 10 PV metrics do not reproduce the frozen summary")
    gate("annualized_estimate_label_exact", data.pv.annualized_label == "ANNUALIZED ESTIMATE" and data.pv.annualization["label"] == "ANNUALIZED ESTIMATE", "annualized estimate label missing")
    gate("simple_payback_label_exact", data.pv.payback_label == "SIMPLE PAYBACK", "simple payback label missing")
    gate("behavioral_and_pv_benefits_separate", all(row["gross_decomposition_identity_holds"] for row in data.pv.effect_decomposition["by_capacity"]), "Stage 10 decomposition identity is not preserved")

    return {
        "stage": "11 - full app integration",
        "status": "PASS" if not problems else "FAIL",
        "checks": checks,
        "problems": problems,
        "frozen_upstream": {
            "expected_file_count": FROZEN_STAGE1_TO_STAGE10_FILE_COUNT,
            "file_count": count,
            "expected_tree_sha256": FROZEN_STAGE1_TO_STAGE10_TREE_SHA256,
            "tree_sha256": tree_hash,
            "byte_identical": checks["frozen_stages1_through10_byte_identical"],
        },
        "loaded": {
            "history_hours": len(data.history),
            "forecast_hours_by_horizon": {horizon.value: len(data.forecasts[horizon].points) for horizon in Horizon},
            "flexibility_components": len(data.flexibility),
            "stage9_hours": len(data.optimization.hourly),
            "stage9_shifted_events": len(data.optimization.shifted_events),
            "pv_capacities_kwp": [row.capacity_kwp for row in data.pv.rows],
        },
    }
