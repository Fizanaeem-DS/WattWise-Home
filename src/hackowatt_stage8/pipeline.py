"""Build and validate the Stage 8 rooftop-PV production artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from .acquire import load_or_acquire
from .config import (
    ASPECT_DEGREES_PVGIS,
    DEMO_CAPACITIES_KWP,
    EXAMPLES_OUTPUT,
    FIGURES_DIR,
    FROZEN_UPSTREAM_FILE_COUNT,
    FROZEN_UPSTREAM_MANIFEST_SHA256,
    HOURLY_OUTPUT,
    HOURLY_SOURCE_YEAR,
    LATITUDE,
    LONGITUDE,
    MONTHLY_OUTPUT,
    MOUNTING_PLACE,
    PROJECT_ROOT,
    PVGIS_API_VERSION,
    PVGIS_SOURCE,
    PV_TECHNOLOGY,
    RAW_OUTPUT,
    REFERENCE_CAPACITY_KWP,
    STAGE2_INPUT,
    SYSTEM_LOSS_PERCENT,
    TILT_DEGREES,
    TIMEZONE,
    TRACKING_TYPE,
    VALIDATION_OUTPUT,
)
from .engine import build_hourly_rows, build_monthly_rows
from .figures import monthly_chart, profile_chart


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(paths: Iterable[Path]) -> tuple[str, dict[str, str]]:
    files = sorted({path for path in paths if path.is_file() and "__pycache__" not in path.parts})
    entries = {path.relative_to(PROJECT_ROOT).as_posix(): sha256(path) for path in files}
    payload = "".join(f"{path}\t{digest}\n" for path, digest in entries.items())
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), entries


def upstream_manifest() -> tuple[str, dict[str, str]]:
    candidates: list[Path] = []
    for root in ("data", "models", "artifacts", "docs", "scripts", "src", "tests"):
        candidates.extend((PROJECT_ROOT / root).rglob("*"))
    candidates.extend(PROJECT_ROOT / name for name in ("README.md", ".gitignore"))
    return _manifest(
        path for path in candidates
        if "stage8" not in path.relative_to(PROJECT_ROOT).as_posix().lower()
    )


def assert_frozen() -> dict[str, Any]:
    digest, files = upstream_manifest()
    if digest != FROZEN_UPSTREAM_MANIFEST_SHA256 or len(files) != FROZEN_UPSTREAM_FILE_COUNT:
        raise RuntimeError(
            f"STOP: frozen Stage 1-6B inventory changed: files={len(files)}, sha256={digest}"
        )
    return {"file_count": len(files), "manifest_sha256": digest}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _correlation(left: list[float], right: list[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_ss = sum((value - left_mean) ** 2 for value in left)
    right_ss = sum((value - right_mean) ** 2 for value in right)
    return numerator / math.sqrt(left_ss * right_ss)


def _provenance(raw: dict[str, Any]) -> dict[str, Any]:
    pvcalc = raw["requests"]["PVcalc"]
    seriescalc = raw["requests"]["seriescalc"]
    response_inputs = pvcalc["response"]["inputs"]
    return {
        "source": PVGIS_SOURCE,
        "api_version": PVGIS_API_VERSION,
        "endpoints": {"annual_monthly": pvcalc["endpoint"], "hourly": seriescalc["endpoint"]},
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "elevation_m_from_pvgis": response_inputs["location"]["elevation"],
        "pv_technology": PV_TECHNOLOGY,
        "mounting_type": "fixed ventilated/free-standing array",
        "pvgis_mountingplace": MOUNTING_PLACE,
        "tilt_degrees": TILT_DEGREES,
        "azimuth_degrees_pvgis_convention": ASPECT_DEGREES_PVGIS,
        "azimuth_interpretation": "0 degrees is south; +90 west; -90 east",
        "system_losses_percent": SYSTEM_LOSS_PERCENT,
        "tracking_type": TRACKING_TYPE,
        "reference_capacity_kwp": REFERENCE_CAPACITY_KWP,
        "annual_monthly_radiation_database": response_inputs["meteo_data"]["radiation_db"],
        "annual_monthly_meteorological_database": response_inputs["meteo_data"]["meteo_db"],
        "annual_monthly_source_year_range": [
            response_inputs["meteo_data"]["year_min"], response_inputs["meteo_data"]["year_max"]
        ],
        "hourly_source_year": HOURLY_SOURCE_YEAR,
        "retrieved_at_utc": raw["retrieved_at_utc"],
        "request_parameters": {
            "PVcalc": pvcalc["parameters"], "seriescalc": seriescalc["parameters"]
        },
        "timezone_treatment": (
            "PVGIS seriescalc times are UTC. Each HH:10 record is converted with the Europe/Madrid IANA zone, "
            "assigned to its containing local clock hour, and matched by month/day/hour to the frozen 2025 timeline."
        ),
    }


def run(refresh_pvgis: bool = False) -> dict[str, Any]:
    before = assert_frozen()
    raw = load_or_acquire(refresh=refresh_pvgis)
    stage2 = _read_csv(STAGE2_INPUT)
    hourly = build_hourly_rows(raw, stage2)
    monthly, annual = build_monthly_rows(raw)

    if len(hourly) != 1464 or [row["timestamp"] for row in hourly] != [row["timestamp"] for row in stage2]:
        raise RuntimeError("STOP: PV output does not align exactly with the 1464 frozen Stage 2 timestamps")
    if any(float(row["pv_generation_kwh_per_kwp"]) < 0 for row in hourly):
        raise RuntimeError("STOP: PVGIS returned negative PV production")
    source_night = [row for row in hourly if float(row["pvgis_sun_height_degrees"]) <= 0]
    if any(float(row["pv_generation_kwh_per_kwp"]) != 0 for row in source_night):
        raise RuntimeError("STOP: PVGIS reports non-zero PV generation when source sun height is non-positive")

    _write_csv(HOURLY_OUTPUT, hourly)
    _write_csv(MONTHLY_OUTPUT, monthly)
    provenance = _provenance(raw)
    examples = []
    for capacity in DEMO_CAPACITIES_KWP:
        examples.append({
            "capacity_kwp": capacity,
            "annual_generation_kwh": round(annual * capacity, 6),
            "monthly_generation_kwh": [
                {
                    "month": row["month"],
                    "generation_kwh": round(row["monthly_generation_kwh_per_kwp"] * capacity, 6),
                }
                for row in monthly
            ],
        })
    EXAMPLES_OUTPUT.write_text(json.dumps({
        "stage": "8",
        "scope": "pv_generation_only",
        "provenance": provenance,
        "reference_system": {
            "capacity_kwp": REFERENCE_CAPACITY_KWP,
            "annual_generation_kwh_per_kwp": annual,
            "monthly_generation_kwh_per_kwp": [
                {"month": row["month"], "generation_kwh_per_kwp": row["monthly_generation_kwh_per_kwp"]}
                for row in monthly
            ],
        },
        "capacity_examples_are_comparisons_not_optima": True,
        "capacity_examples": examples,
        "optimization_implemented": False,
        "economics_implemented": False,
        "battery_implemented": False,
        "stage9_started": False,
        "stage10_started": False,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    pv = [float(row["pv_generation_kwh_per_kwp"]) for row in hourly]
    solar = [float(row["shortwave_radiation"]) for row in stage2]
    daylight_positions = [index for index, value in enumerate(solar) if value > 0]
    stage2_dark_positions = [index for index, value in enumerate(solar) if value == 0]
    validation = {
        "stage": "8",
        "frozen_upstream": before,
        "raw_source_sha256": sha256(RAW_OUTPUT),
        "hourly_row_count": len(hourly),
        "unique_timestamp_count": len({row["timestamp"] for row in hourly}),
        "first_timestamp": hourly[0]["timestamp"],
        "last_timestamp": hourly[-1]["timestamp"],
        "timezone": TIMEZONE,
        "all_nonnegative": all(value >= 0 for value in pv),
        "pvgis_source_night_hour_count": len(source_night),
        "pvgis_source_night_nonzero_count": sum(
            float(row["pv_generation_kwh_per_kwp"]) != 0 for row in source_night
        ),
        "annual_generation_kwh_per_kwp": annual,
        "monthly_generation_sum_kwh_per_kwp": sum(
            float(row["monthly_generation_kwh_per_kwp"]) for row in monthly
        ),
        "monthly_count": len(monthly),
        "stage2_shortwave_vs_pv_correlation_all_hours": _correlation(solar, pv),
        "stage2_shortwave_vs_pv_correlation_daylight_hours": _correlation(
            [solar[index] for index in daylight_positions], [pv[index] for index in daylight_positions]
        ),
        "stage2_zero_shortwave_hour_count": len(stage2_dark_positions),
        "stage2_zero_shortwave_with_positive_pv_count": sum(pv[index] > 0 for index in stage2_dark_positions),
        "stage2_solar_use": "descriptive sanity check only; no Stage 2 radiation value tunes or produces PV output",
    }
    VALIDATION_OUTPUT.write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    monthly_chart(FIGURES_DIR / "pv_monthly_generation.svg", monthly)
    profile_chart(FIGURES_DIR / "pv_aug_sep_profile.svg", hourly)

    after = assert_frozen()
    if after != before:
        raise RuntimeError("STOP: frozen Stage 1-6B files changed during Stage 8")
    return {
        "hourly_rows": len(hourly),
        "annual_generation_kwh_per_kwp": annual,
        "monthly_values": len(monthly),
        "frozen_upstream": after,
    }


def main(refresh_pvgis: bool = False) -> int:
    print(json.dumps(run(refresh_pvgis=refresh_pvgis), indent=2, sort_keys=True))
    return 0
