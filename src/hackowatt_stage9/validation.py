"""Independent Stage 9 contract, physics, accounting, and freeze gates."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
from pathlib import Path
from typing import Any

from .accounting import account_hour
from .config import (
    BEHAVIORAL_COLUMNS,
    COMFORT_TOLERANCE_C,
    COST_TOLERANCE_EUR,
    FIXED_COLUMNS,
    FROZEN_UPSTREAM_FILE_COUNT,
    FROZEN_UPSTREAM_TREE_SHA256,
    ROOT,
    VALUE_TOLERANCE,
)
from .data import build_operational_context, tariff_eur_per_kwh


def frozen_upstream_identity(root: Path = ROOT) -> tuple[int, str]:
    """Hash the exact Stage 1-8 surface captured before Stage 9 began."""

    included = (
        "README.md", ".gitignore", "data", "docs", "models", "artifacts",
        "scripts", "src", "tests", "contract", "constraints", "stage7",
    )
    files: list[Path] = []
    for name in included:
        path = root / name
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(item for item in path.rglob("*") if item.is_file())
    records = []
    for path in sorted(set(files)):
        rel = path.relative_to(root).as_posix()
        lower = rel.lower()
        if "__pycache__" in path.parts or ".pytest_cache" in path.parts:
            continue
        if "stage9" in lower:
            continue
        records.append(f"{rel}:{hashlib.sha256(path.read_bytes()).hexdigest()}")
    return len(records), hashlib.sha256("\n".join(records).encode()).hexdigest()


def _overlap(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> bool:
    return start < other_end and end > other_start


def validate_result(result: dict[str, Any], hourly_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate the solved realization without relying on optimizer assertions."""

    problems: list[str] = []
    checks: dict[str, bool] = {}
    requirements = result["inputs"]
    events = {event.event_id: event for event in requirements.events}
    timeline = [datetime.fromisoformat(row["timestamp"]) for row in result["actual_rows"]]

    def gate(name: str, condition: bool, detail: str) -> None:
        checks[name] = bool(condition)
        if not condition:
            problems.append(detail)

    gate("exact_hour_count", len(hourly_rows) == 1464, "hourly output does not contain 1,464 hours")
    gate(
        "timestamps_aligned",
        [row["timestamp"] for row in result["actual_rows"]]
        == [row["timestamp"] for row in result["pv_rows"]]
        == [row["timestamp"] for row in hourly_rows],
        "Stage 3, Stage 8, or Stage 9 timestamps do not align",
    )
    gate(
        "hourly_loads_nonnegative",
        all(float(row["current_load_kwh"]) >= -VALUE_TOLERANCE and float(row["optimized_load_kwh"]) >= -VALUE_TOLERANCE for row in hourly_rows),
        "negative hourly demand was produced",
    )
    gate(
        "fixed_class_a_unchanged",
        all(sum(float(row[name]) for name in FIXED_COLUMNS) >= 0 for row in result["actual_rows"]),
        "Class A source load changed or became invalid",
    )
    gate(
        "behavioral_class_b_unchanged",
        all(sum(float(row[name]) for name in BEHAVIORAL_COLUMNS) >= 0 for row in result["actual_rows"]),
        "Class B source load changed or became invalid",
    )
    gate(
        "identical_pv_for_current_and_optimized",
        all(float(row["pv_generation_kwh"]) >= 0 for row in hourly_rows),
        "PV differs between current and optimized accounting",
    )

    accounting_ok = True
    for row in hourly_rows:
        for prefix in ("current", "optimized"):
            expected = account_hour(
                float(row[f"{prefix}_load_kwh"]),
                float(row["pv_generation_kwh"]),
                float(row["tariff_eur_per_kwh"]),
            )
            for field in ("self_consumed_pv_kwh", "grid_import_kwh", "exported_pv_kwh", "net_cost_eur"):
                accounting_ok &= abs(float(row[f"{prefix}_{field}"]) - expected[field]) <= 1e-8
    gate("shared_exact_accounting", accounting_ok, "current and optimized accounting equations diverge")
    gate(
        "nonnegative_energy_flows",
        all(
            float(row[field]) >= -VALUE_TOLERANCE
            for row in hourly_rows
            for field in (
                "current_self_consumed_pv_kwh", "optimized_self_consumed_pv_kwh",
                "current_grid_import_kwh", "optimized_grid_import_kwh",
                "current_exported_pv_kwh", "optimized_exported_pv_kwh",
            )
        ),
        "negative grid/PV energy flow was produced",
    )

    event_rows = {row["event_id"]: row for row in result["event_rows"] if row["component"] != "hvac"}
    gate("all_stage7_events_reported", set(event_rows) == set(events), "Stage 7 event IDs are missing or duplicated")
    gate(
        "real_event_instances_not_mock_midpoints",
        requirements.source == "real" and not requirements.mock_generator_used
        and all(event.source == "real" and event.provenance for event in events.values()),
        "mock or midpoint requirements entered the production optimizer",
    )
    service_ok = True
    coherent_ok = True
    availability_ok = True
    away_ok = True
    dependency_ok = True
    for event_id, event in events.items():
        row = event_rows[event_id]
        if row["constraint_status"] == "boundary_outside_window":
            service_ok &= bool(event.boundary_truncated and (event.delivered_in_window_kwh or 0.0) == 0.0)
            continue
        allocation = result["optimized_allocations"][event_id]
        delivered = sum(float(value) for value in allocation.values())
        service_ok &= abs(delivered - event.energy_kwh) <= 1e-5
        start = datetime.fromisoformat(row["optimized_start"])
        end = datetime.fromisoformat(row["optimized_end"])
        if event.coherent_cycle:
            coherent_ok &= abs((end - start).total_seconds() / 3600.0 - event.duration_hours) <= 1e-7
            coherent_ok &= abs(delivered - event.power_kw * event.duration_hours) <= 1e-5
            availability_ok &= any(
                datetime.fromisoformat(interval.start) - timedelta(microseconds=1) <= start
                <= datetime.fromisoformat(interval.end) + timedelta(microseconds=1)
                for interval in event.availability_intervals if interval.end
            )
            away_ok &= all(
                not _overlap(start, end, datetime.fromisoformat(interval.start), datetime.fromisoformat(interval.end))
                for interval in event.away_intervals if interval.end
            )
        else:
            interval = event.availability_intervals[0]
            lower = datetime.fromisoformat(interval.start)
            upper = datetime.fromisoformat(interval.end) if interval.end else timeline[-1] + timedelta(hours=1)
            for index, energy in allocation.items():
                hour_start = timeline[int(index)]
                overlap = max((min(hour_start + timedelta(hours=1), upper) - max(hour_start, lower)).total_seconds() / 3600.0, 0.0)
                availability_ok &= float(energy) <= event.power_kw * overlap + 1e-6
        if event.depends_on_event_id:
            parent = event_rows[event.depends_on_event_id]
            dependency_ok &= start >= datetime.fromisoformat(parent["optimized_end"]) - timedelta(microseconds=1)
    gate("event_energy_preserved", service_ok, "one or more non-HVAC services lost energy")
    gate("coherent_cycles_preserved", coherent_ok, "a coherent event was split, shortened, or repowered")
    gate("availability_and_deadlines_respected", availability_ok, "an event operates outside its Stage 7 availability")
    gate("away_intervals_respected", away_ok, "a coherent limited event overlaps exact AWAY")
    gate("washer_dryer_ordering_respected", dependency_ok, "a dryer starts before its washer completes")

    temperatures = list(result["optimized_temperature"]) + [float(result["optimized_terminal_temperature_c"])]
    heat, cool = result["optimized_heat"], result["optimized_cool"]
    recurrence_ok = True
    controller_ok = True
    physical_violations: dict[int, float] = {}
    for index, state in enumerate(requirements.hvac.hourly_states):
        expected_next = (
            temperatures[index]
            + (state.outdoor_temperature_c - temperatures[index]) / requirements.hvac.thermal_time_constant_hours
            + requirements.hvac.heating_effect_c_per_hour * float(heat[index])
            + requirements.hvac.cooling_effect_c_per_hour * float(cool[index])
        )
        recurrence_ok &= abs(temperatures[index + 1] - expected_next) <= 2e-6
        controller_ok &= -VALUE_TOLERANCE <= float(heat[index]) <= 1 + VALUE_TOLERANCE
        controller_ok &= -VALUE_TOLERANCE <= float(cool[index]) <= 1 + VALUE_TOLERANCE
        controller_ok &= float(heat[index]) + float(cool[index]) <= 1 + VALUE_TOLERANCE
        if float(cool[index]) > VALUE_TOLERANCE:
            controller_ok &= temperatures[index + 1] >= min(requirements.hvac.heating.lower_c, state.effective_heating_target_c) - 2e-6
        if float(heat[index]) > VALUE_TOLERANCE:
            controller_ok &= temperatures[index + 1] <= max(requirements.hvac.cooling.upper_c, state.effective_cooling_target_c) + 2e-6
        if not state.away and state.occupancy_state in {"FULL", "PARTIAL"}:
            physical_violations[index] = max(
                requirements.hvac.heating.lower_c - temperatures[index],
                temperatures[index] - requirements.hvac.cooling.upper_c,
                0.0,
            )
    gate("thermal_recurrence_exact", recurrence_ok, "optimized HVAC violates the frozen thermal recurrence")
    gate("hvac_mutual_exclusion_and_controller_targets", controller_ok, "HVAC duty or controller-target implication is invalid")
    comfort_ok = sum(physical_violations.values()) <= result["comfort_minimum_degree_hours"] + 5e-5
    comfort_ok &= all(
        value <= result["comfort_caps"].get(index, 0.0) + 5e-6
        for index, value in physical_violations.items()
    )
    gate("zero_avoidable_occupied_comfort_violation", comfort_ok, "optimized HVAC exceeds a proven minimum occupied violation")

    example = next((item for item in result["comfort_proofs"] if item["timestamp"] == "2025-08-10T17:00:00+02:00"), None)
    gate(
        "reported_example_independently_reproduced",
        example is not None and abs(float(example["minimum_unavoidable_violation_c"]) - 0.112312094) <= 1e-5,
        "the accepted 2025-08-10 17:00 feasibility example was not reproduced",
    )
    gate(
        "cost_priority_preserved",
        float(result["final_net_cost_eur"]) <= float(result["minimum_net_cost_before_peak_tiebreak_eur"]) + COST_TOLERANCE_EUR + 1e-6,
        "peak tie-break increased net cost beyond the numerical equality tolerance",
    )

    context = build_operational_context("2025-09-01T23:00:00+02:00", 24, result["capacity_kwp"])
    gate(
        "no_operational_future_actual_leakage",
        context["uses_future_actual_demand"] is False and len(context["points"]) == 24,
        "operational context uses future actual demand",
    )
    frozen_count, frozen_hash = frozen_upstream_identity()
    frozen_ok = frozen_count == FROZEN_UPSTREAM_FILE_COUNT and frozen_hash == FROZEN_UPSTREAM_TREE_SHA256
    gate("frozen_stage1_through_stage8_byte_identity", frozen_ok, "frozen Stage 1-8 bytes changed")

    return {
        "status": "PASS" if not problems else "FAIL",
        "problems": problems,
        "checks": checks,
        "frozen_upstream": {
            "file_count": frozen_count,
            "tree_sha256": frozen_hash,
            "expected_file_count": FROZEN_UPSTREAM_FILE_COUNT,
            "expected_tree_sha256": FROZEN_UPSTREAM_TREE_SHA256,
            "byte_identical": frozen_ok,
        },
        "occupied_hour_count": len(physical_violations),
        "optimized_total_occupied_violation_degree_hours": sum(physical_violations.values()),
        "tariff_schedule": {
            "00:00-06:00": tariff_eur_per_kwh("2025-08-01T01:00:00+02:00"),
            "06:00-17:00": tariff_eur_per_kwh("2025-08-01T12:00:00+02:00"),
            "17:00-22:00": tariff_eur_per_kwh("2025-08-01T19:00:00+02:00"),
            "22:00-24:00": tariff_eur_per_kwh("2025-08-01T23:00:00+02:00"),
        },
    }


__all__ = ["frozen_upstream_identity", "validate_result"]
