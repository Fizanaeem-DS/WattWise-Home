"""Acquire and preserve the raw Open-Meteo response."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import (
    END_DATE,
    HOURLY_VARIABLES,
    LATITUDE,
    LONGITUDE,
    MODEL,
    RAW_JSON_PATH,
    RAW_METADATA_PATH,
    SOURCE_API,
    SOURCE_DOCUMENTATION,
    SOURCE_NAME,
    START_DATE,
    TIMEZONE,
)


def build_request_url() -> str:
    params = {
        "latitude": f"{LATITUDE:.4f}",
        "longitude": f"{LONGITUDE:.4f}",
        "start_date": START_DATE,
        "end_date": END_DATE,
        "hourly": ",".join(HOURLY_VARIABLES),
        "timezone": TIMEZONE,
        "models": MODEL,
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "timeformat": "iso8601",
    }
    return f"{SOURCE_API}?{urlencode(params)}"


def _check_payload(payload: dict) -> None:
    if payload.get("error"):
        raise RuntimeError(f"Open-Meteo error: {payload.get('reason', 'unknown error')}")
    hourly = payload.get("hourly")
    units = payload.get("hourly_units")
    if not isinstance(hourly, dict) or not isinstance(units, dict):
        raise ValueError("Open-Meteo response lacks hourly data or hourly_units")
    missing = [name for name in ("time", *HOURLY_VARIABLES) if name not in hourly]
    missing_units = [name for name in ("time", *HOURLY_VARIABLES) if name not in units]
    if missing or missing_units:
        raise ValueError(
            f"Open-Meteo response incomplete: data missing={missing}, units missing={missing_units}"
        )


def acquire(
    raw_path: Path = RAW_JSON_PATH,
    metadata_path: Path = RAW_METADATA_PATH,
) -> dict:
    """Fetch once, write the exact response bytes, and record acquisition metadata."""
    url = build_request_url()
    request = Request(url, headers={"User-Agent": "HackoWatt-Scenario3-Stage2/1.0"})
    retrieved_at = datetime.now(timezone.utc).isoformat()

    with urlopen(request, timeout=60) as response:
        raw_bytes = response.read()
        status = response.status
        response_headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() in {"content-type", "date", "etag", "last-modified"}
        }

    payload = json.loads(raw_bytes.decode("utf-8"))
    _check_payload(payload)

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw_bytes)

    metadata = {
        "source": SOURCE_NAME,
        "api_endpoint": SOURCE_API,
        "documentation": SOURCE_DOCUMENTATION,
        "request_url": url,
        "requested_at_utc": retrieved_at,
        "http_status": status,
        "http_response_headers": response_headers,
        "raw_file": str(raw_path.relative_to(raw_path.parents[2])).replace("\\", "/"),
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "requested": {
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
            "timezone": TIMEZONE,
            "start_date": START_DATE,
            "end_date": END_DATE,
            "hourly_variables": list(HOURLY_VARIABLES),
            "model": MODEL,
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
            "timeformat": "iso8601",
        },
        "returned": {
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
            "elevation": payload.get("elevation"),
            "timezone": payload.get("timezone"),
            "timezone_abbreviation": payload.get("timezone_abbreviation"),
            "utc_offset_seconds": payload.get("utc_offset_seconds"),
            "generationtime_ms": payload.get("generationtime_ms"),
            "hourly_variables": [
                key for key in payload["hourly"] if key != "time"
            ],
            "hourly_units": payload["hourly_units"],
            "row_count": len(payload["hourly"]["time"]),
        },
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return metadata

