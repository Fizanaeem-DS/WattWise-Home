"""End-to-end Stage 9 artifact pipeline."""

from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from .config import EVENT_OUTPUT, FIGURES_DIR, HOURLY_OUTPUT, SUMMARY_OUTPUT
from .figures import cost_chart, line_chart
from .optimizer import optimize_retrospective
from .reporting import build_hourly_rows, build_summary
from .validation import validate_result


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _schedule_fingerprint(result: dict[str, Any], hourly: list[dict[str, Any]]) -> str:
    schedule = {
        "hourly": [
            {
                "timestamp": row["timestamp"],
                "optimized_load_kwh": row["optimized_load_kwh"],
                "optimized_indoor_temperature_c": row["optimized_indoor_temperature_c"],
                "optimized_heating_duty_fraction": row["optimized_heating_duty_fraction"],
                "optimized_cooling_duty_fraction": row["optimized_cooling_duty_fraction"],
            }
            for row in hourly
        ],
        "events": result["event_rows"],
    }
    return _canonical_hash(schedule)


def run(verify_determinism: bool = True) -> dict[str, Any]:
    """Solve, independently validate, then write only Stage 9 outputs."""

    result = optimize_retrospective()
    hourly = build_hourly_rows(result)
    validation = validate_result(result, hourly)
    if validation["status"] != "PASS":
        raise RuntimeError("STOP: Stage 9 validation failed: " + "; ".join(validation["problems"]))

    fingerprint = _schedule_fingerprint(result, hourly)
    rerun_fingerprint = fingerprint
    deterministic = True
    if verify_determinism:
        rerun = optimize_retrospective()
        rerun_hourly = build_hourly_rows(rerun)
        rerun_fingerprint = _schedule_fingerprint(rerun, rerun_hourly)
        deterministic = fingerprint == rerun_fingerprint
        if not deterministic:
            raise RuntimeError("STOP: deterministic rerun produced a different Stage 9 schedule")

    summary = build_summary(result, hourly)
    summary["validation"] = validation
    summary["determinism"] = {
        "verified_by_full_second_solve": verify_determinism,
        "identical_schedule": deterministic,
        "schedule_sha256": fingerprint,
        "rerun_schedule_sha256": rerun_fingerprint,
    }
    summary["solver_objectives"] = {
        "minimum_unavoidable_occupied_violation_degree_hours": result["comfort_minimum_degree_hours"],
        "minimum_net_cost_before_peak_tiebreak_eur": result["minimum_net_cost_before_peak_tiebreak_eur"],
        "final_net_cost_eur": result["final_net_cost_eur"],
        "optimized_peak_kwh": result["optimized_peak_kwh"],
    }

    _write_csv(HOURLY_OUTPUT, hourly)
    _write_csv(EVENT_OUTPUT, result["event_rows"])
    _write_json(SUMMARY_OUTPUT, summary)

    start = datetime.fromisoformat(summary["representative_week"]["start"]).date()
    end = datetime.fromisoformat(summary["representative_week"]["end_exclusive"]).date()
    week = [row for row in hourly if start <= datetime.fromisoformat(row["timestamp"]).date() < end]
    line_chart(
        FIGURES_DIR / "representative_week_current_vs_optimized.svg",
        "Representative week: current load, optimized load, and PV",
        week,
        [
            ("current_load_kwh", "Current load", "#d95f02"),
            ("optimized_load_kwh", "Optimized load", "#1b9e77"),
            ("pv_generation_kwh", "PV generation", "#7570b3"),
        ],
    )
    line_chart(
        FIGURES_DIR / "representative_week_grid_import.svg",
        "Representative week: current and optimized grid import",
        week,
        [
            ("current_grid_import_kwh", "Current grid import", "#d95f02"),
            ("optimized_grid_import_kwh", "Optimized grid import", "#1b9e77"),
        ],
    )
    cost_chart(FIGURES_DIR / "representative_week_cost.svg", week)
    return summary


__all__ = ["run"]
