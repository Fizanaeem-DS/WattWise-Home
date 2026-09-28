"""Independent temporal, completeness, physical, and solar validation."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path

from .config import (
    EXPECTED_END_LOCAL,
    EXPECTED_NOMINAL_ROWS,
    EXPECTED_START_LOCAL,
    HOURLY_VARIABLES,
    PROCESSED_CSV_PATH,
    RAW_JSON_PATH,
    TIMEZONE,
    VALIDATION_REPORT_PATH,
)


def _load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _number(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _all_between(values: list[float | None], lower: float, upper: float) -> bool:
    return all(value is not None and lower <= value <= upper for value in values)


def _all_at_least(values: list[float | None], lower: float) -> bool:
    return all(value is not None and value >= lower for value in values)


def validate(
    processed_path: Path = PROCESSED_CSV_PATH,
    raw_path: Path = RAW_JSON_PATH,
    report_path: Path = VALIDATION_REPORT_PATH,
) -> dict:
    rows = _load_rows(processed_path)
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    timestamps = [datetime.fromisoformat(row["timestamp"]) for row in rows]
    timestamps_utc = [value.astimezone(timezone.utc) for value in timestamps]

    expected_start = datetime.fromisoformat(EXPECTED_START_LOCAL)
    expected_end = datetime.fromisoformat(EXPECTED_END_LOCAL)
    expected_timestamps = []
    cursor = expected_start
    while cursor <= expected_end:
        expected_timestamps.append(cursor)
        cursor += timedelta(hours=1)

    timestamp_set = set(timestamps)
    missing_hours = [value.isoformat() for value in expected_timestamps if value not in timestamp_set]
    duplicate_count = len(timestamps) - len(timestamp_set)
    ordered = all(a < b for a, b in zip(timestamps_utc, timestamps_utc[1:]))
    continuity = all(
        b - a == timedelta(hours=1)
        for a, b in zip(timestamps_utc, timestamps_utc[1:])
    )

    values = {
        variable: [_number(row.get(variable)) for row in rows]
        for variable in HOURLY_VARIABLES
    }
    missingness = {}
    for variable, series in values.items():
        missing = sum(value is None for value in series)
        missingness[variable] = {
            "missing_count": missing,
            "coverage_percent": round(100.0 * (len(rows) - missing) / len(rows), 6)
            if rows
            else 0.0,
        }

    temp_present = [value for value in values["temperature_2m"] if value is not None]
    humidity_ok = _all_between(values["relative_humidity_2m"], 0.0, 100.0)
    precipitation_ok = _all_at_least(values["precipitation"], 0.0)
    cloud_ok = _all_between(values["cloud_cover"], 0.0, 100.0)
    wind_ok = _all_at_least(values["wind_speed_10m"], 0.0)
    solar_nonnegative = all(
        _all_at_least(values[name], 0.0)
        for name in ("shortwave_radiation", "direct_radiation", "diffuse_radiation")
    )

    coherence_errors = []
    for ghi, direct, diffuse in zip(
        values["shortwave_radiation"],
        values["direct_radiation"],
        values["diffuse_radiation"],
    ):
        if None in (ghi, direct, diffuse):
            continue
        coherence_errors.append(abs(ghi - (direct + diffuse)))
    max_coherence_error = max(coherence_errors, default=math.nan)
    # These local hours are fully dark in Barcelona during Aug-Sep. Because the
    # API's radiation values are means of the preceding hour, 00:00-04:00 is a
    # deliberately conservative core-night window.
    core_night_indices = [index for index, value in enumerate(timestamps) if value.hour <= 4]
    nighttime_all_zero = all(
        values[name][index] == 0.0
        for index in core_night_indices
        for name in ("shortwave_radiation", "direct_radiation", "diffuse_radiation")
    )
    daylight_dates = {
        timestamp.date()
        for timestamp, ghi in zip(timestamps, values["shortwave_radiation"])
        if ghi is not None and ghi > 0.0
    }
    all_dates = {timestamp.date() for timestamp in timestamps}
    daylight_each_day = daylight_dates == all_dates

    units = raw["hourly_units"]
    checks = {
        "row_count_matches_nominal": len(rows) == EXPECTED_NOMINAL_ROWS,
        "expected_start": bool(timestamps and timestamps[0] == expected_start),
        "expected_end": bool(timestamps and timestamps[-1] == expected_end),
        "strictly_chronological": ordered,
        "no_duplicate_timestamps": duplicate_count == 0,
        "no_missing_hours": not missing_hours,
        "hourly_continuity": continuity,
        "all_timestamps_timezone_aware": all(value.tzinfo is not None for value in timestamps),
        "no_missing_values": all(
            result["missing_count"] == 0 for result in missingness.values()
        ),
        "humidity_within_0_100_percent": humidity_ok,
        "precipitation_nonnegative": precipitation_ok,
        "cloud_cover_within_0_100_percent": cloud_ok,
        "wind_speed_nonnegative": wind_ok,
        "solar_variables_nonnegative": solar_nonnegative,
        "temperature_within_broad_integrity_bounds": bool(temp_present)
        and min(temp_present) >= -100.0
        and max(temp_present) <= 60.0,
        "solar_ghi_equals_direct_plus_diffuse_within_0_2_w_m2": (
            bool(coherence_errors) and max_coherence_error <= 0.2
        ),
        "core_night_solar_is_zero": nighttime_all_zero,
        "positive_shortwave_radiation_present_each_day": daylight_each_day,
    }

    report = {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "temporal": {
            "raw_row_count": len(raw["hourly"]["time"]),
            "processed_row_count": len(rows),
            "expected_nominal_row_count": EXPECTED_NOMINAL_ROWS,
            "first_timestamp": timestamps[0].isoformat() if timestamps else None,
            "last_timestamp": timestamps[-1].isoformat() if timestamps else None,
            "strictly_chronological": ordered,
            "duplicate_timestamp_count": duplicate_count,
            "missing_hour_count": len(missing_hours),
            "missing_hours": missing_hours,
            "hourly_continuity": continuity,
            "timezone": TIMEZONE,
            "observed_utc_offsets": sorted(
                {value.strftime("%z") for value in timestamps}
            ),
        },
        "missingness": missingness,
        "physical_sanity": {
            "humidity_within_0_100_percent": humidity_ok,
            "precipitation_nonnegative": precipitation_ok,
            "cloud_cover_within_0_100_percent": cloud_ok,
            "wind_speed_nonnegative": wind_ok,
            "temperature_min_c": min(temp_present) if temp_present else None,
            "temperature_max_c": max(temp_present) if temp_present else None,
            "temperature_integrity_bounds_c": [-100.0, 60.0],
            "temperature_within_integrity_bounds": checks[
                "temperature_within_broad_integrity_bounds"
            ],
            "solar_variables_nonnegative": solar_nonnegative,
        },
        "solar_sanity": {
            "definition_used": (
                "Open-Meteo preceding-hour means on the horizontal plane: "
                "shortwave radiation (GHI) = direct radiation + diffuse radiation."
            ),
            "max_abs_ghi_minus_direct_plus_diffuse_w_m2": (
                round(max_coherence_error, 6) if coherence_errors else None
            ),
            "coherence_tolerance_w_m2": 0.2,
            "coherent_within_tolerance": checks[
                "solar_ghi_equals_direct_plus_diffuse_within_0_2_w_m2"
            ],
            "core_night_local_hours_inclusive": [0, 4],
            "core_night_observation_count": len(core_night_indices),
            "core_night_all_three_solar_variables_zero": nighttime_all_zero,
            "positive_shortwave_radiation_present_each_day": daylight_each_day,
        },
        "units": {name: units[name] for name in ("time", *HOURLY_VARIABLES)},
    }
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report

