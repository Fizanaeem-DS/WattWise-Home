"""Frozen data adapters with explicit operational/retrospective separation."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from hackowatt_stage8 import get_pv_generation
from .config import STAGE3C_HOURLY, STAGE6B_FORECAST


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def tariff_eur_per_kwh(timestamp: str) -> float:
    hour = datetime.fromisoformat(timestamp).hour
    if hour < 6:
        return 0.18
    if hour < 17:
        return 0.28
    if hour < 22:
        return 0.40
    return 0.28


def load_retrospective_inputs(capacity_kwp: float) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Load actual Stage 3 only for retrospective validation."""

    actual = read_csv(STAGE3C_HOURLY)
    pv = get_pv_generation(capacity_kwp)
    if [row["timestamp"] for row in actual] != [row["timestamp"] for row in pv]:
        raise RuntimeError("STOP: Stage 3 and Stage 8 timestamps do not align")
    return actual, pv


def stage6_display_lookup() -> dict[str, dict[str, float | str]]:
    """Choose the shortest-lead frozen forecast available for each timestamp."""

    selected: dict[str, dict[str, str]] = {}
    for row in read_csv(STAGE6B_FORECAST):
        current = selected.get(row["timestamp"])
        key = (int(row["lead_hour"]), row["forecast_origin"], int(row["horizon_hours"]))
        if current is None or key < (
            int(current["lead_hour"]), current["forecast_origin"], int(current["horizon_hours"])
        ):
            selected[row["timestamp"]] = row
    return {
        timestamp: {
            "stage6_expected_demand_kwh": float(row["point_forecast_kwh"]),
            "current_peak_risk": float(row["peak_probability"]),
            "stage6_p95_kwh": float(row["p95_kwh"]),
            "forecast_origin": row["forecast_origin"],
        }
        for timestamp, row in selected.items()
    }


def build_operational_context(
    forecast_origin: str,
    horizon_hours: int,
    capacity_kwp: float,
) -> dict[str, Any]:
    """Build forecast-only context; never opens Stage 3 actual-demand data."""

    rows = [
        row for row in read_csv(STAGE6B_FORECAST)
        if row["forecast_origin"] == forecast_origin and int(row["horizon_hours"]) == horizon_hours
    ]
    if not rows:
        raise ValueError("No frozen Stage 6B forecast for the requested origin/horizon")
    rows.sort(key=lambda row: int(row["lead_hour"]))
    pv_lookup = {row["timestamp"]: row for row in get_pv_generation(capacity_kwp)}
    points = []
    for row in rows:
        pv = pv_lookup.get(row["timestamp"])
        if pv is None:
            raise ValueError("Requested operational horizon extends beyond the Stage 8 profile")
        points.append({
            "timestamp": row["timestamp"],
            "expected_demand_kwh": float(row["point_forecast_kwh"]),
            "p95_kwh": float(row["p95_kwh"]),
            "peak_probability": float(row["peak_probability"]),
            "pv_generation_kwh": float(pv["pv_generation_kwh"]),
            "tariff_eur_per_kwh": tariff_eur_per_kwh(row["timestamp"]),
        })
    return {
        "mode": "operational",
        "forecast_origin": forecast_origin,
        "horizon_hours": horizon_hours,
        "capacity_kwp": float(capacity_kwp),
        "uses_future_actual_demand": False,
        "event_requirements": "must be supplied from information available at the forecast origin",
        "points": points,
    }

