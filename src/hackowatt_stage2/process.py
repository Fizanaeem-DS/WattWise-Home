"""Convert the preserved response to a clean, timezone-explicit CSV."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import (
    DATASET_METADATA_PATH,
    EXPECTED_UNITS,
    HOURLY_VARIABLES,
    PROCESSED_CSV_PATH,
    RAW_JSON_PATH,
    RAW_METADATA_PATH,
    TIMEZONE,
)


def _validate_source_shape(payload: dict) -> int:
    hourly = payload["hourly"]
    lengths = {name: len(hourly[name]) for name in ("time", *HOURLY_VARIABLES)}
    if len(set(lengths.values())) != 1:
        raise ValueError(f"Hourly arrays have different lengths: {lengths}")
    if payload.get("timezone") != TIMEZONE:
        raise ValueError(
            f"Unexpected response timezone {payload.get('timezone')!r}; expected {TIMEZONE!r}"
        )
    returned_units = payload["hourly_units"]
    mismatches = {
        name: {"expected": unit, "returned": returned_units.get(name)}
        for name, unit in EXPECTED_UNITS.items()
        if returned_units.get(name) != unit
    }
    if mismatches:
        raise ValueError(f"Unexpected Open-Meteo units: {mismatches}")
    return lengths["time"]


def process(
    raw_path: Path = RAW_JSON_PATH,
    raw_metadata_path: Path = RAW_METADATA_PATH,
    output_path: Path = PROCESSED_CSV_PATH,
    dataset_metadata_path: Path = DATASET_METADATA_PATH,
) -> dict:
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    acquisition = json.loads(raw_metadata_path.read_text(encoding="utf-8"))
    row_count = _validate_source_shape(payload)
    zone = ZoneInfo(TIMEZONE)

    rows = []
    for index, raw_timestamp in enumerate(payload["hourly"]["time"]):
        # Open-Meteo returns local wall-clock ISO strings when timezone is set.
        # Attach the requested IANA zone and serialize the UTC offset explicitly.
        timestamp = __import__("datetime").datetime.fromisoformat(raw_timestamp)
        if timestamp.tzinfo is not None:
            raise ValueError(f"Expected a local wall-clock timestamp, got {raw_timestamp}")
        timestamp = timestamp.replace(tzinfo=zone)
        row = {"timestamp": timestamp.isoformat()}
        row.update({name: payload["hourly"][name][index] for name in HOURLY_VARIABLES})
        rows.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("timestamp", *HOURLY_VARIABLES))
        writer.writeheader()
        writer.writerows(rows)

    metadata = {
        "dataset": "HackoWatt Scenario 3 Stage 2 Barcelona hourly weather and solar",
        "processed_file": str(output_path.relative_to(output_path.parents[2])).replace(
            "\\", "/"
        ),
        "source_raw_file": acquisition["raw_file"],
        "source_raw_sha256": acquisition["raw_sha256"],
        "row_count": row_count,
        "columns": ["timestamp", *HOURLY_VARIABLES],
        "timezone": TIMEZONE,
        "timestamp_processing": (
            "Open-Meteo local wall-clock ISO 8601 values were assigned the requested "
            "Europe/Madrid IANA timezone and serialized with an explicit UTC offset."
        ),
        "value_conversions": "None. Source values and returned units are preserved.",
        "units": {"timestamp": f"ISO 8601 with {TIMEZONE} UTC offset", **{
            name: payload["hourly_units"][name] for name in HOURLY_VARIABLES
        }},
        "requested_coordinates": {
            "latitude": acquisition["requested"]["latitude"],
            "longitude": acquisition["requested"]["longitude"],
        },
        "returned_grid_cell": {
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
            "elevation_m": payload.get("elevation"),
        },
        "source": acquisition["source"],
        "api_endpoint": acquisition["api_endpoint"],
        "model": acquisition["requested"]["model"],
        "retrieved_at_utc": acquisition["requested_at_utc"],
    }
    dataset_metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return metadata

