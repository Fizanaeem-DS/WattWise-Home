"""Programmatic acceptance validation for the deterministic Stage 3C join."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any

from .config import (
    FINAL_ENERGY_COLUMNS,
    HOURLY_OUTPUT,
    METADATA_OUTPUT,
    SOURCE_PATHS,
    STAGE2_INPUT,
    STAGE3A_COMPONENT_COLUMNS,
    STAGE3A_INPUT,
    STAGE3B_COMPONENT_COLUMNS,
    STAGE3B_INPUT,
    STAGE3B_LEDGER,
    VALIDATION_OUTPUT,
    WEATHER_COLUMNS,
)


def _read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes())
    return digest.hexdigest()


def validate(
    stage2_path: Path = STAGE2_INPUT,
    stage3a_path: Path = STAGE3A_INPUT,
    stage3b_path: Path = STAGE3B_INPUT,
    stage3b_ledger_path: Path = STAGE3B_LEDGER,
    hourly_path: Path = HOURLY_OUTPUT,
    metadata_path: Path = METADATA_OUTPUT,
    report_path: Path = VALIDATION_OUTPUT,
) -> dict[str, Any]:
    _, stage2 = _read(stage2_path)
    _, stage3a = _read(stage3a_path)
    _, stage3b = _read(stage3b_path)
    columns, rows = _read(hourly_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    timestamps = [datetime.fromisoformat(row["timestamp"]) for row in rows]
    utc = [timestamp.astimezone(timezone.utc) for timestamp in timestamps]

    stage3a_preserved = all(
        row[column] == source[column]
        for row, source in zip(rows, stage3a)
        for column in (*STAGE3A_COMPONENT_COLUMNS, "stage3a_total_kwh")
    )
    stage3b_preserved = all(
        row[column] == source[column]
        for row, source in zip(rows, stage3b)
        for column in (*STAGE3B_COMPONENT_COLUMNS, "stage3b_total_kwh")
    )
    weather_preserved = all(
        row[column] == source[column]
        for row, source in zip(rows, stage2)
        for column in WEATHER_COLUMNS
    )
    household_exact = all(
        Decimal(row["household_total_kwh"])
        == Decimal(source_a["stage3a_total_kwh"]) + Decimal(source_b["stage3b_total_kwh"])
        for row, source_a, source_b in zip(rows, stage3a, stage3b)
    )
    categories_exact = all(
        Decimal(row["base_fixed_kwh"])
        == Decimal(row["refrigerator_kwh"]) + Decimal(row["smart_home_base_kwh"])
        and Decimal(row["routine_behavior_kwh"])
        == sum((Decimal(row[column]) for column in STAGE3A_COMPONENT_COLUMNS[2:]), Decimal(0))
        and Decimal(row["ev_kwh"]) == Decimal(row["ev_total_kwh"])
        and Decimal(row["pool_kwh"])
        == Decimal(row["pool_circulation_kwh"]) + Decimal(row["pool_heating_kwh"])
        and abs(
            Decimal(row["household_total_kwh"])
            - (
                Decimal(row["base_fixed_kwh"])
                + Decimal(row["routine_behavior_kwh"])
                + Decimal(row["hvac_kwh"])
                + Decimal(row["ev_kwh"])
                + Decimal(row["pool_kwh"])
                + Decimal(row["sauna_kwh"])
            )
        )
        <= Decimal("1e-9")
        for row in rows
    )
    nonnegative = all(Decimal(row[column]) >= 0 for row in rows for column in FINAL_ENERGY_COLUMNS)

    stage3a_total = sum((Decimal(row["stage3a_total_kwh"]) for row in rows), Decimal(0))
    stage3b_total = sum((Decimal(row["stage3b_total_kwh"]) for row in rows), Decimal(0))
    household_total = sum((Decimal(row["household_total_kwh"]) for row in rows), Decimal(0))
    metadata_totals = metadata["energy_totals_kwh"]
    metadata_reconciles = (
        abs(Decimal(str(metadata_totals["stage3a"])) - stage3a_total) <= Decimal("5e-9")
        and abs(Decimal(str(metadata_totals["stage3b"])) - stage3b_total) <= Decimal("5e-9")
        and abs(Decimal(str(metadata_totals["household"])) - household_total) <= Decimal("5e-9")
    )

    ev_ledger = json.loads(stage3b_ledger_path.read_text(encoding="utf-8"))
    truncated = [event for event in ev_ledger["ev_charging_events"] if event["boundary_truncated"]]
    ledger_remainder = sum((Decimal(str(event["remaining_energy_kwh"])) for event in truncated), Decimal(0))
    boundary = metadata["ev_post_boundary_accounting"]
    boundary_documented = (
        boundary["boundary_truncated_event_count"] == len(truncated)
        and abs(Decimal(str(boundary["remaining_energy_outside_profile_kwh"])) - ledger_remainder)
        <= Decimal("5e-9")
        and boundary["included_in_hourly_profile"] is False
    )
    source_hashes_match = all(
        metadata["source_sha256"].get(name) == _sha256(path)
        for name, path in SOURCE_PATHS.items()
    )

    checks = {
        "exactly_1464_rows": len(rows) == 1_464,
        "exact_stage2_timestamps": [row["timestamp"] for row in rows] == [row["timestamp"] for row in stage2],
        "exact_stage3a_timestamps": [row["timestamp"] for row in rows] == [row["timestamp"] for row in stage3a],
        "exact_stage3b_timestamps": [row["timestamp"] for row in rows] == [row["timestamp"] for row in stage3b],
        "no_duplicate_timestamps": len(timestamps) == len(set(timestamps)),
        "no_missing_hours": all(b - a == timedelta(hours=1) for a, b in zip(utc, utc[1:])),
        "timezone_preserved": all(timestamp.utcoffset() == timedelta(hours=2) for timestamp in timestamps),
        "expected_timestamp_range": bool(rows)
        and rows[0]["timestamp"] == "2025-08-01T00:00:00+02:00"
        and rows[-1]["timestamp"] == "2025-09-30T23:00:00+02:00",
        "stage3a_components_and_total_preserved_exactly": stage3a_preserved,
        "stage3b_components_and_total_preserved_exactly": stage3b_preserved,
        "stage2_weather_preserved_exactly": weather_preserved,
        "household_total_exact_source_combination": household_exact,
        "category_reconciliation_exact": categories_exact,
        "no_negative_energy": nonnegative,
        "metadata_totals_reconcile": metadata_reconciles,
        "source_hashes_match": source_hashes_match,
        "ev_boundary_remainder_documented_and_excluded": boundary_documented and household_exact,
        "no_new_behavioral_assumptions": metadata["behavioral_assumptions_added"] == [],
        "top_10_diagnostics_present": len(metadata["top_10_highest_demand_hours"]) == 10,
        "required_output_columns_present": set(FINAL_ENERGY_COLUMNS) <= set(columns),
    }
    report = {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "row_count": len(rows),
        "first_timestamp": rows[0]["timestamp"] if rows else None,
        "last_timestamp": rows[-1]["timestamp"] if rows else None,
        "energy_totals_kwh": metadata_totals,
        "ev_post_boundary_accounting": boundary,
    }
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report
