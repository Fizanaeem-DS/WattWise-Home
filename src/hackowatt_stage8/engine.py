"""Normalize PVGIS data and expose capacity-scaled Stage 8 interfaces."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import math
from numbers import Real
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .config import HOURLY_OUTPUT, MONTHLY_OUTPUT, REFERENCE_CAPACITY_KWP, TIMEZONE


def validate_capacity(capacity_kwp: Any) -> float:
    if isinstance(capacity_kwp, bool) or not isinstance(capacity_kwp, Real):
        raise ValueError("capacity_kwp must be a finite positive number")
    value = float(capacity_kwp)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("capacity_kwp must be a finite positive number")
    return value


def parse_pvgis_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d:%H%M").replace(tzinfo=timezone.utc)


def hourly_lookup(
    raw: dict[str, Any], calendar_months: set[int]
) -> dict[tuple[int, int, int], dict[str, Any]]:
    zone = ZoneInfo(TIMEZONE)
    rows = raw["requests"]["seriescalc"]["response"]["outputs"]["hourly"]
    lookup: dict[tuple[int, int, int], dict[str, Any]] = {}
    for row in rows:
        utc = parse_pvgis_utc(row["time"])
        local = utc.astimezone(zone)
        if local.month not in calendar_months:
            continue
        key = (local.month, local.day, local.hour)
        if key in lookup:
            raise RuntimeError(f"STOP: duplicate PVGIS local calendar hour {key}")
        lookup[key] = {
            "pvgis_utc": utc,
            "pvgis_local": local,
            "power_w": float(row["P"]),
            "sun_height_degrees": float(row["H_sun"]),
        }
    return lookup


def build_hourly_rows(raw: dict[str, Any], stage2_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    target_timestamps = [datetime.fromisoformat(row["timestamp"]) for row in stage2_rows]
    lookup = hourly_lookup(raw, {timestamp.month for timestamp in target_timestamps})
    output: list[dict[str, Any]] = []
    for weather, target in zip(stage2_rows, target_timestamps):
        source = lookup.get((target.month, target.day, target.hour))
        if source is None:
            raise RuntimeError(f"STOP: PVGIS source hour missing for {weather['timestamp']}")
        output.append({
            "timestamp": weather["timestamp"],
            "reference_capacity_kwp": REFERENCE_CAPACITY_KWP,
            "pv_generation_kwh_per_kwp": source["power_w"] / 1000.0,
            "pvgis_power_w_per_kwp": source["power_w"],
            "pvgis_sun_height_degrees": source["sun_height_degrees"],
            "pvgis_source_year": source["pvgis_local"].year,
            "pvgis_utc_timestamp": source["pvgis_utc"].isoformat(),
            "pvgis_local_timestamp": source["pvgis_local"].isoformat(),
            "timezone_treatment": "PVGIS UTC converted to Europe/Madrid; local HH:10 assigned to containing local clock hour",
            "source": "PVGIS 5.3 seriescalc",
        })
    return output


def build_monthly_rows(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    response = raw["requests"]["PVcalc"]["response"]
    monthly = response["outputs"]["monthly"]["fixed"]
    annual = float(response["outputs"]["totals"]["fixed"]["E_y"])
    if len(monthly) != 12:
        raise RuntimeError(f"STOP: expected 12 PVGIS monthly values, received {len(monthly)}")
    rows = [{
        "month": int(item["month"]),
        "reference_capacity_kwp": REFERENCE_CAPACITY_KWP,
        "monthly_generation_kwh_per_kwp": float(item["E_m"]),
        "monthly_share_of_annual_generation": float(item["E_m"]) / annual,
        "annual_generation_kwh_per_kwp": annual,
        "source": "PVGIS 5.3 PVcalc long-term monthly average",
    } for item in monthly]
    return rows, annual


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def get_pv_generation(capacity_kwp: Any) -> list[dict[str, Any]]:
    """Return the frozen Aug-Sep hourly PV profile scaled to a positive capacity."""
    capacity = validate_capacity(capacity_kwp)
    return [{
        "timestamp": row["timestamp"],
        "capacity_kwp": capacity,
        "pv_generation_kwh": float(row["pv_generation_kwh_per_kwp"]) * capacity,
    } for row in _read_csv(HOURLY_OUTPUT)]


def get_annual_pv_summary(capacity_kwp: Any) -> dict[str, Any]:
    """Return PVGIS annual/monthly production scaled to a positive capacity."""
    capacity = validate_capacity(capacity_kwp)
    rows = _read_csv(MONTHLY_OUTPUT)
    annual_per_kwp = float(rows[0]["annual_generation_kwh_per_kwp"])
    return {
        "capacity_kwp": capacity,
        "annual_generation_kwh": annual_per_kwp * capacity,
        "monthly_generation_kwh": [
            {
                "month": int(row["month"]),
                "generation_kwh": float(row["monthly_generation_kwh_per_kwp"]) * capacity,
            }
            for row in rows
        ],
    }
